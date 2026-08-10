"""Trasporto degli eventi di progresso import (SPEC §51) su Redis Streams,
non pub/sub: un CSV piccolo puo' finire di essere processato prima che il
client apra la connessione SSE (scenario del tutto normale, non un caso
limite), e col pub/sub fire-and-forget ogni evento emesso in quella finestra
andrebbe perso — il DoD "job trackabile via SSE" (docs/ROADMAP.md §04) non
sarebbe verificabile. Con uno Stream il client rilegge da `0-0` tutto cio'
che e' gia' stato emesso e poi passa a `XREAD BLOCK` per gli eventi live.
"""
import json
import time
import uuid
from collections.abc import AsyncIterator

from app.core.config import get_settings
from app.core.redis import redis_client

TERMINAL_EVENTS = frozenset({"job.completed", "job.failed", "job.cancelled"})
_STREAM_MAXLEN = 1000
_BLOCK_MS = 15_000  # anche heartbeat: se non arriva nulla, si manda un ping SSE


def _stream_key(import_id: uuid.UUID) -> str:
    return f"lumio:jobs:import:{import_id}:events"


async def emit(import_id: uuid.UUID, event: str, **payload) -> None:
    """Registra un evento SPEC §51 (`job.created`, `job.progress`, ...).

    Payload indicativo di SPEC §51: {job_id, type, stage, progress, message}.
    Qui si aggiungono sempre `event` e `import_id`; il chiamante passa il
    resto come kwargs. Mai contenuto finanziario nel payload (SPEC §55).
    """
    key = _stream_key(import_id)
    data = json.dumps({"event": event, "import_id": str(import_id), **payload})
    await redis_client.xadd(key, {"data": data}, maxlen=_STREAM_MAXLEN, approximate=True)
    await redis_client.expire(key, get_settings().job_events_ttl_seconds)


def _decode_entry(fields: dict[bytes, bytes]) -> dict:
    return json.loads(fields[b"data"])


def _format_sse(payload: dict) -> str:
    return f"event: {payload['event']}\ndata: {json.dumps(payload)}\n\n"


async def stream(import_id: uuid.UUID) -> AsyncIterator[str]:
    """Genera le righe SSE per un import: prima il replay di tutto cio' che
    e' gia' stato emesso (chiude la race del job finito prima che il client
    si colleghi), poi eventi live via XREAD BLOCK con heartbeat, fino a un
    evento terminale o a un cap massimo di durata (nessuna connessione deve
    restare appesa se il worker muore senza emettere ne' completed ne'
    failed).
    """
    key = _stream_key(import_id)
    deadline = time.monotonic() + get_settings().import_job_timeout_seconds + 60

    last_id = "0-0"
    for entry_id, fields in await redis_client.xrange(key, min="-", max="+"):
        last_id = entry_id.decode()
        payload = _decode_entry(fields)
        yield _format_sse(payload)
        if payload["event"] in TERMINAL_EVENTS:
            return

    while time.monotonic() < deadline:
        result = await redis_client.xread({key: last_id}, block=_BLOCK_MS, count=50)
        if not result:
            yield ": ping\n\n"
            continue
        _stream_name, entries = result[0]
        for entry_id, fields in entries:
            last_id = entry_id.decode()
            payload = _decode_entry(fields)
            yield _format_sse(payload)
            if payload["event"] in TERMINAL_EVENTS:
                return
    yield _format_sse({"event": "job.failed", "message": "timeout in attesa di aggiornamenti"})

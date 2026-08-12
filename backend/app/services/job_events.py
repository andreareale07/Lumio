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


def _stream_key(topic_id: uuid.UUID, namespace: str) -> str:
    return f"lumio:jobs:{namespace}:{topic_id}:events"


async def emit(topic_id: uuid.UUID, event: str, *, namespace: str = "import", **payload) -> None:
    """Registra un evento SPEC §51 (`job.created`, `job.progress`, ...).

    `namespace` distingue lo stream per tipo di job (default "import", per
    non toccare i call site esistenti): milestone 10 lo usa anche per
    `namespace="google_export"` con `topic_id=workspace_id` (un solo export
    per workspace alla volta, stesso `_job_id` fisso dell'enqueue arq).

    Payload indicativo di SPEC §51: {job_id, type, stage, progress, message}.
    Qui si aggiungono sempre `event` e l'id del topic (chiave generica
    `topic_id`, non piu' `import_id`: nessun consumer frontend legge questo
    campo dal payload, lo conosce gia' dall'URL). Mai contenuto finanziario
    nel payload (SPEC §55).
    """
    key = _stream_key(topic_id, namespace)
    data = json.dumps({"event": event, "topic_id": str(topic_id), **payload})
    await redis_client.xadd(key, {"data": data}, maxlen=_STREAM_MAXLEN, approximate=True)
    await redis_client.expire(key, get_settings().job_events_ttl_seconds)


def _decode_entry(fields: dict[bytes, bytes]) -> dict:
    return json.loads(fields[b"data"])


def _format_sse(payload: dict) -> str:
    return f"event: {payload['event']}\ndata: {json.dumps(payload)}\n\n"


async def stream(
    topic_id: uuid.UUID, *, namespace: str = "import", timeout_seconds: int | None = None
) -> AsyncIterator[str]:
    """Genera le righe SSE per un job: prima il replay di tutto cio' che
    e' gia' stato emesso (chiude la race del job finito prima che il client
    si colleghi), poi eventi live via XREAD BLOCK con heartbeat, fino a un
    evento terminale o a un cap massimo di durata (nessuna connessione deve
    restare appesa se il worker muore senza emettere ne' completed ne'
    failed).

    `timeout_seconds` di default resta quello dell'import (comportamento
    invariato per il call site esistente); un nuovo `namespace` (es.
    l'export Google Sheets) passa il proprio timeout esplicitamente.
    """
    key = _stream_key(topic_id, namespace)
    if timeout_seconds is None:
        timeout_seconds = get_settings().import_job_timeout_seconds
    deadline = time.monotonic() + timeout_seconds + 60

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

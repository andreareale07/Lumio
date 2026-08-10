"""Test del trasporto eventi su Redis Streams, isolato dall'endpoint HTTP
(quello si testa in test_import_events.py insieme all'autorizzazione).
Verifica in particolare il DoD (a): il replay deve restituire gli eventi
gia' emessi anche se il consumer si collega dopo che il job e' finito.
"""
import asyncio
import json
import uuid

from app.services import job_events


async def _collect_until_terminal(import_id: uuid.UUID) -> list[dict]:
    collected = []
    async for line in job_events.stream(import_id):
        if line.startswith(": ping"):
            continue
        payload = json.loads(line.split("data: ", 1)[1])
        collected.append(payload)
        if payload["event"] in job_events.TERMINAL_EVENTS:
            break
    return collected


async def test_replay_returns_events_emitted_before_client_connected():
    import_id = uuid.uuid4()

    # Il job "finisce" prima che qualunque client si sia mai collegato allo
    # stream — esattamente lo scenario che il pub/sub perderebbe.
    await job_events.emit(import_id, "job.created", job_id="abc")
    await job_events.emit(import_id, "job.started")
    await job_events.emit(import_id, "job.progress", progress=50)
    await job_events.emit(import_id, "job.completed", transactions_imported=3)

    events = await _collect_until_terminal(import_id)

    assert [e["event"] for e in events] == [
        "job.created",
        "job.started",
        "job.progress",
        "job.completed",
    ]
    assert events[0]["job_id"] == "abc"
    assert events[2]["progress"] == 50


async def test_stream_stops_after_terminal_event_even_with_more_writes_ignored():
    import_id = uuid.uuid4()
    await job_events.emit(import_id, "job.created")
    await job_events.emit(import_id, "job.failed", message="errore")

    events = await _collect_until_terminal(import_id)

    assert [e["event"] for e in events] == ["job.created", "job.failed"]


async def test_live_event_is_picked_up_after_replay_completes():
    import_id = uuid.uuid4()
    await job_events.emit(import_id, "job.created")

    async def _emit_completion_later():
        await asyncio.sleep(0.2)
        await job_events.emit(import_id, "job.completed")

    asyncio.ensure_future(_emit_completion_later())
    events = await _collect_until_terminal(import_id)

    assert [e["event"] for e in events] == ["job.created", "job.completed"]

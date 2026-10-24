"""Interruzione delle attivita' del motore AI (classificazione di un import e
riclassificazione): stato 'cancelled', segnale cooperativo, API."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.config import get_settings
from app.db.rls import rls_session
from app.models.job_run import JobRun
from app.services.ai_classification import ClassificationAttempt
from app.services.job_cancellation import is_cancel_requested, request_cancel
from app.worker.jobs import ai_classification_job, reclassification_job
from app.worker.jobs.ai_classification_job import classify_import_transactions_job
from app.worker.jobs.reclassification_job import reclassify_workspace_job
from tests.test_ai_classification_job import _auth_headers, _create_account, _register
from tests.test_ai_engine_api import _activate_profile, _completed_import, _events
from tests.test_recompute_positions import _owner

NO_MATCH = ClassificationAttempt(result=None, provider_error=False)


async def _setup(client, email: str, rows: int = 5) -> tuple[str, str, str]:
    token = await _register(client, email)
    account_id = await _create_account(client, token)
    await _activate_profile(client, token)
    import_id, user_id = await _completed_import(client, token, account_id, rows=rows)
    return token, import_id, user_id


async def _import_status(client, token: str, import_id: str) -> dict:
    return (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).json()


async def test_cancelling_a_queued_classification_is_immediate_and_the_job_then_skips(client):
    token, import_id, user_id = await _setup(client, "cancel-queued@example.com")
    assert (await _import_status(client, token, import_id))["ai_classification_status"] == "pending"

    cancel = await client.post(f"/api/v1/ai-engine/imports/{import_id}/cancel", headers=_auth_headers(token))
    assert cancel.status_code == 202, cancel.text
    assert cancel.json() == {"ai_status": "cancelled", "stopping": False}
    assert (await _import_status(client, token, import_id))["ai_classification_status"] == "cancelled"

    # Quando il worker arrivera' a eseguirlo trova lo stato e non fa nulla.
    await classify_import_transactions_job(None, import_id, user_id)
    assert (await _import_status(client, token, import_id))["ai_classification_status"] == "cancelled"

    events = (await _events(client, token))["items"]
    assert any(e["code"] == "cancelled_by_user" and e["import_id"] == import_id for e in events)

    status = (await client.get("/api/v1/ai-engine/status", headers=_auth_headers(token))).json()
    row = next(i for i in status["recent_imports"] if i["import_id"] == import_id)
    assert (row["ai_status"], row["can_cancel"], row["can_retry"]) == ("cancelled", False, True)

    retry = await client.post(f"/api/v1/ai-engine/imports/{import_id}/retry", headers=_auth_headers(token))
    assert retry.status_code == 202
    assert retry.json()["ai_status"] == "pending"


async def test_cancelling_a_running_classification_sets_the_stop_signal(client):
    token, import_id, user_id = await _setup(client, "cancel-running@example.com")
    async with rls_session(uuid.UUID(user_id)) as db:
        await db.execute(text("UPDATE imports SET ai_classification_status = 'running' WHERE id = :i"), {"i": import_id})
        await db.commit()

    cancel = await client.post(f"/api/v1/ai-engine/imports/{import_id}/cancel", headers=_auth_headers(token))
    assert cancel.status_code == 202, cancel.text
    assert cancel.json() == {"ai_status": "running", "stopping": True}
    assert await is_cancel_requested("ai_classification", uuid.UUID(import_id))


async def test_running_classification_stops_between_batches_and_keeps_what_it_did(client, monkeypatch):
    concurrency = get_settings().ai_max_concurrency
    token, import_id, user_id = await _setup(client, "cancel-job@example.com", rows=concurrency * 3)
    calls: list[int] = []

    async def fake_classify(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            # L'utente preme "Interrompi" mentre il primo gruppo e' in volo.
            await request_cancel("ai_classification", uuid.UUID(import_id))
        return NO_MATCH

    monkeypatch.setattr(ai_classification_job, "classify_transaction", fake_classify)
    await classify_import_transactions_job(None, import_id, user_id)

    detail = await _import_status(client, token, import_id)
    assert detail["ai_classification_status"] == "cancelled"
    # Si e' fermato dopo il primo gruppo, non ha scorso tutta la coda.
    assert len(calls) == concurrency
    assert not await is_cancel_requested("ai_classification", uuid.UUID(import_id))

    events = (await _events(client, token))["items"]
    stopped = next(e for e in events if e["code"] == "cancelled_by_user")
    assert f"total={concurrency * 3}" in stopped["message"]
    assert stopped["severity"] == "warning"


async def test_a_stale_stop_signal_does_not_cancel_the_next_run(client, monkeypatch):
    token, import_id, user_id = await _setup(client, "cancel-stale@example.com")
    await request_cancel("ai_classification", uuid.UUID(import_id))
    seen: list[int] = []

    async def fake_classify(*args, **kwargs):
        seen.append(1)
        return NO_MATCH

    monkeypatch.setattr(ai_classification_job, "classify_transaction", fake_classify)
    await classify_import_transactions_job(None, import_id, user_id)

    assert (await _import_status(client, token, import_id))["ai_classification_status"] == "completed"
    assert len(seen) > 0


async def test_cancel_without_a_running_classification_is_rejected(client):
    token, import_id, user_id = await _setup(client, "cancel-none@example.com")
    await client.post(f"/api/v1/ai-engine/imports/{import_id}/cancel", headers=_auth_headers(token))
    again = await client.post(f"/api/v1/ai-engine/imports/{import_id}/cancel", headers=_auth_headers(token))
    assert again.status_code == 409

    intruder = await _register(client, "cancel-intruder@example.com")
    foreign = await client.post(f"/api/v1/ai-engine/imports/{import_id}/cancel", headers=_auth_headers(intruder))
    assert foreign.status_code == 404


async def test_activity_offers_cancel_only_while_the_job_is_active(client):
    token, import_id, user_id = await _setup(client, "cancel-activity@example.com")

    items = (await client.get("/api/v1/activity", headers=_auth_headers(token))).json()["items"]
    ai_item = next(i for i in items if i["kind"] == "ai_classification")
    assert ai_item["cancel_url"] == f"/ai-engine/imports/{import_id}/cancel"

    await client.post(f"/api/v1/ai-engine/imports/{import_id}/cancel", headers=_auth_headers(token))
    items = (await client.get("/api/v1/activity", headers=_auth_headers(token))).json()["items"]
    assert not any(i["kind"] == "ai_classification" for i in items)


async def test_reclassification_cancel_requires_a_running_job(client):
    token = await _register(client, "cancel-reclass-none@example.com")
    none_running = await client.post("/api/v1/classification/reclassify/cancel", headers=_auth_headers(token))
    assert none_running.status_code == 409


async def test_reclassification_cancel_sets_the_signal_and_the_activity_link(client):
    email = "cancel-reclass-api@example.com"
    token, import_id, user_id = await _setup(client, email)
    user, workspace_id = await _owner(email)
    async with rls_session(user) as db:
        db.add(
            JobRun(
                workspace_id=workspace_id,
                job_kind="reclassification",
                status="running",
                job_id="fake",
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()

    items = (await client.get("/api/v1/activity", headers=_auth_headers(token))).json()["items"]
    reclass = next(i for i in items if i["kind"] == "reclassification")
    assert reclass["cancel_url"] == "/classification/reclassify/cancel"

    cancel = await client.post("/api/v1/classification/reclassify/cancel", headers=_auth_headers(token))
    assert cancel.status_code == 202
    assert await is_cancel_requested("reclassification", workspace_id)


async def test_reclassification_with_ai_stops_when_asked_and_ends_as_cancelled(client, monkeypatch):
    email = "cancel-reclass-job@example.com"
    token, import_id, user_id = await _setup(client, email, rows=6)
    user, workspace_id = await _owner(email)
    calls: list[int] = []

    async def fake_classify(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            await request_cancel("reclassification", workspace_id)
        return NO_MATCH

    monkeypatch.setattr(reclassification_job, "classify_transaction", fake_classify)
    await reclassify_workspace_job(None, str(workspace_id), str(user), "uncategorized", True)

    assert len(calls) == 1
    status = (await client.get("/api/v1/classification/reclassify/status", headers=_auth_headers(token))).json()
    assert status["status"] == "cancelled"
    assert status["message"].startswith("Interrotta dall'utente")
    assert not await is_cancel_requested("reclassification", workspace_id)

    events = (await _events(client, token))["items"]
    assert any(e["code"] == "cancelled_by_user" and e["run_kind"] == "reclassification" for e in events)


async def test_reclassification_stops_in_the_rule_phase_too(client, monkeypatch):
    email = "cancel-reclass-rules@example.com"
    token, import_id, user_id = await _setup(client, email, rows=4)
    user, workspace_id = await _owner(email)

    async def always_cancelled(kind, topic_id):
        return True

    monkeypatch.setattr(reclassification_job, "is_cancel_requested", always_cancelled)
    await reclassify_workspace_job(None, str(workspace_id), str(user), "uncategorized", False)

    status = (await client.get("/api/v1/classification/reclassify/status", headers=_auth_headers(token))).json()
    assert status["status"] == "cancelled"

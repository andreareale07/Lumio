"""API di manutenzione: ricalcolo posizioni lanciabile da UI, con anteprima e un
resoconto persistito di cosa e' cambiato (`job_runs.details`)."""
from datetime import UTC, datetime
from decimal import Decimal

from app.db.rls import rls_session
from app.models.job_run import JobRun
from app.worker.jobs.positions_recompute_job import positions_recompute_job
from tests.test_portfolio_api import _auth_headers, _register
from tests.test_recompute_positions import _corrupt_realized, _setup, _stored_realized


async def test_preview_reports_changes_without_writing(client):
    token_email = "maint-preview@example.com"
    user_id, _ = await _setup(client, token_email)
    token = (
        await client.post("/api/v1/auth/login", json={"email": token_email, "password": "correct-password-123"})
    ).json()["access_token"]
    await _corrupt_realized(user_id, "777.00")

    response = await client.get("/api/v1/maintenance/positions-recompute/preview", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["checked"], body["changed"]) == (1, 1)
    assert body["changes"][0]["old_realized_pl"] == "777.00"
    assert body["changes"][0]["new_realized_pl"] == "100.00"
    assert body["changes"][0]["account"] == "Trade Republic"
    assert await _stored_realized(user_id) == Decimal("777.00")


async def test_trigger_returns_202_and_job_id(client):
    token = await _register(client, "maint-trigger@example.com")
    response = await client.post("/api/v1/maintenance/positions-recompute", headers=_auth_headers(token))
    assert response.status_code == 202
    assert response.json()["job_id"]


async def test_trigger_while_running_returns_same_job_without_double_enqueue(client):
    email = "maint-double@example.com"
    user_id, workspace_id = await _setup(client, email)
    token = (
        await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-password-123"})
    ).json()["access_token"]
    async with rls_session(user_id) as db:
        db.add(
            JobRun(
                workspace_id=workspace_id,
                job_kind="positions_recompute",
                status="running",
                job_id="fake-recompute-job",
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()

    response = await client.post("/api/v1/maintenance/positions-recompute", headers=_auth_headers(token))
    assert response.status_code == 202
    assert response.json()["job_id"] == "fake-recompute-job"


async def test_job_leaves_a_persisted_report_of_what_changed(client):
    email = "maint-report@example.com"
    user_id, workspace_id = await _setup(client, email)
    token = (
        await client.post("/api/v1/auth/login", json={"email": email, "password": "correct-password-123"})
    ).json()["access_token"]

    assert (
        await client.get("/api/v1/maintenance/positions-recompute/status", headers=_auth_headers(token))
    ).json() is None

    await _corrupt_realized(user_id, "999999.99")
    await positions_recompute_job(None, str(workspace_id), str(user_id))

    run = (
        await client.get("/api/v1/maintenance/positions-recompute/status", headers=_auth_headers(token))
    ).json()
    assert run["status"] == "success"
    assert run["message"] == "1 posizioni aggiornate su 1 controllate."
    details = run["details"]
    assert (details["checked"], details["changed"], details["truncated"]) == (1, 1, False)
    assert details["changes"][0]["old_realized_pl"] == "999999.99"
    assert details["changes"][0]["new_realized_pl"] == "100.00"
    assert await _stored_realized(user_id) == Decimal("100.00")

    await positions_recompute_job(None, str(workspace_id), str(user_id))
    second = (
        await client.get("/api/v1/maintenance/positions-recompute/status", headers=_auth_headers(token))
    ).json()
    assert second["details"]["changed"] == 0
    assert second["details"]["changes"] == []
    # Una riesecuzione a vuoto NON cancella la traccia di cosa era cambiato.
    carried = second["details"]["previous_changes"]
    assert carried["changed"] == 1
    assert carried["changes"][0]["old_realized_pl"] == "999999.99"
    assert carried["at"]

    await positions_recompute_job(None, str(workspace_id), str(user_id))
    third = (
        await client.get("/api/v1/maintenance/positions-recompute/status", headers=_auth_headers(token))
    ).json()
    assert third["details"]["previous_changes"]["changes"][0]["old_realized_pl"] == "999999.99"


async def test_status_and_preview_are_isolated_between_workspaces(client):
    await _setup(client, "maint-iso-a@example.com")
    other_token = await _register(client, "maint-iso-b@example.com")
    preview = await client.get("/api/v1/maintenance/positions-recompute/preview", headers=_auth_headers(other_token))
    assert preview.json() == {"checked": 0, "changed": 0, "changes": []}

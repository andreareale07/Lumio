"""Motore AI: registro persistente di esecuzioni ed errori, stato e rilancio
manuale (Impostazioni > Motore AI). Gli errori finivano solo nel log del
worker, che l'utente non vede mai."""
import httpx
from httpx import AsyncClient

from app.worker.jobs.ai_classification_job import (
    _MAX_CONSECUTIVE_PROVIDER_ERRORS,
    classify_import_transactions_job,
)
from app.worker.jobs.import_job import import_job
from tests.test_ai_classification_job import _auth_headers, _create_account, _register

OUTAGE_URL = "http://fake-ai-outage.local/v1/chat/completions"


async def _activate_profile(client: AsyncClient, token: str, endpoint: str = "http://fake-ai-outage.local/v1") -> None:
    created = await client.post(
        "/api/v1/settings/ai/profiles",
        json={"name": "Provider", "provider": "custom", "endpoint": endpoint, "model": "local-model"},
        headers=_auth_headers(token),
    )
    await client.post(
        f"/api/v1/settings/ai/profiles/{created.json()['id']}/activate", headers=_auth_headers(token)
    )


async def _completed_import(
    client: AsyncClient, token: str, account_id: str, rows: int = 5, salt: str = "", amount: str = "-10.00"
) -> tuple[str, str]:
    # Descrizioni generiche: nessun livello deterministico le classifica,
    # quindi restano senza categoria e idonee all'AI.
    body = "\n".join(f"2026-01-{15 + i:02d},Pagamento generico presso terzi {salt}{i},{amount}" for i in range(rows))
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", f"data,descrizione,importo\n{body}\n".encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": upload.json()["preview"]["suggested_mapping"]},
        headers=_auth_headers(token),
    )
    user_id = (await client.get("/api/v1/auth/me", headers=_auth_headers(token))).json()["id"]
    await import_job(None, import_id, user_id)
    return import_id, user_id


async def _events(client: AsyncClient, token: str, **params) -> dict:
    response = await client.get("/api/v1/ai-engine/events", params=params, headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


async def test_provider_outage_is_recorded_without_leaking_the_url(client, httpx_mock):
    token = await _register(client, "aie-outage@example.com")
    account_id = await _create_account(client, token)
    await _activate_profile(client, token)
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"), url=OUTAGE_URL)

    import_id, user_id = await _completed_import(client, token, account_id, rows=_MAX_CONSECUTIVE_PROVIDER_ERRORS + 3)
    await classify_import_transactions_job(None, import_id, user_id)

    events = (await _events(client, token))["items"]
    by_code = {e["code"] for e in events}
    assert {"provider_error", "job_interrupted"} <= by_code
    interrupted = next(e for e in events if e["code"] == "job_interrupted")
    assert interrupted["message"] == "provider_unreachable"
    assert interrupted["severity"] == "error"
    assert interrupted["import_id"] == import_id
    assert interrupted["import_filename"] == "estratto.csv"
    # Regola non negoziabile: nessun URL/chiave in una risposta API.
    assert all("fake-ai-outage" not in e["message"] for e in events)

    status = (await client.get("/api/v1/ai-engine/status", headers=_auth_headers(token))).json()
    assert status["errors_last_24h"] >= 1
    assert status["active_profile"]["provider"] == "custom"
    failed = next(i for i in status["recent_imports"] if i["import_id"] == import_id)
    assert failed["ai_status"] == "failed"
    assert failed["can_retry"] is True
    assert failed["uncategorized_eligible"] > 0
    assert status["uncategorized_eligible"] >= failed["uncategorized_eligible"]


async def test_skipped_ai_records_why_it_did_not_start(client):
    token = await _register(client, "aie-noprofile@example.com")
    account_id = await _create_account(client, token)
    import_id, _ = await _completed_import(client, token, account_id)

    events = (await _events(client, token))["items"]
    skipped = next(e for e in events if e["code"] == "skipped_no_profile")
    assert skipped["severity"] == "info"
    assert skipped["import_id"] == import_id

    status = (await client.get("/api/v1/ai-engine/status", headers=_auth_headers(token))).json()
    assert status["active_profile"] is None
    row = next(i for i in status["recent_imports"] if i["import_id"] == import_id)
    assert row["ai_status"] == "skipped"
    assert row["can_retry"] is False

    retry = await client.post(f"/api/v1/ai-engine/imports/{import_id}/retry", headers=_auth_headers(token))
    assert retry.status_code == 409
    assert "profilo AI" in retry.json()["detail"]


async def test_retry_requeues_a_failed_import_and_blocks_double_click(client, httpx_mock):
    token = await _register(client, "aie-retry@example.com")
    account_id = await _create_account(client, token)
    await _activate_profile(client, token)
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"), url=OUTAGE_URL)
    import_id, user_id = await _completed_import(client, token, account_id, rows=_MAX_CONSECUTIVE_PROVIDER_ERRORS + 3)
    await classify_import_transactions_job(None, import_id, user_id)

    retry = await client.post(f"/api/v1/ai-engine/imports/{import_id}/retry", headers=_auth_headers(token))
    assert retry.status_code == 202, retry.text
    assert retry.json()["ai_status"] == "pending"
    assert retry.json()["ai_total"] > 0

    detail = (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).json()
    assert detail["ai_classification_status"] == "pending"
    assert detail["ai_classification_error_message"] is None
    assert detail["ai_transactions_classified"] == 0

    again = await client.post(f"/api/v1/ai-engine/imports/{import_id}/retry", headers=_auth_headers(token))
    assert again.status_code == 409


async def test_retry_unknown_or_foreign_import_is_404(client):
    owner = await _register(client, "aie-owner@example.com")
    intruder = await _register(client, "aie-intruder@example.com")
    account_id = await _create_account(client, owner)
    import_id, _ = await _completed_import(client, owner, account_id)

    foreign = await client.post(f"/api/v1/ai-engine/imports/{import_id}/retry", headers=_auth_headers(intruder))
    assert foreign.status_code == 404


async def test_events_are_isolated_between_workspaces_and_filterable(client):
    owner = await _register(client, "aie-iso-owner@example.com")
    other = await _register(client, "aie-iso-other@example.com")
    account_id = await _create_account(client, owner)
    await _completed_import(client, owner, account_id)

    assert (await _events(client, owner))["total"] >= 1
    assert await _events(client, other) == {"items": [], "total": 0}
    assert (await _events(client, owner, severity="error"))["total"] == 0
    assert (await _events(client, owner, severity="info"))["total"] >= 1

    bad = await client.get(
        "/api/v1/ai-engine/events", params={"severity": "fatal"}, headers=_auth_headers(owner)
    )
    assert bad.status_code == 422


async def test_event_log_is_pruned_to_the_most_recent_events(client, monkeypatch):
    from app.services import ai_run_event_service as service

    monkeypatch.setattr(service, "MAX_EVENTS_PER_WORKSPACE", 3)
    token = await _register(client, "aie-prune@example.com")
    account_id = await _create_account(client, token)
    for n in range(5):
        # Importi distinti: stesso giorno e importo finirebbero in revisione
        # (dedup) e non completerebbero l'import.
        await _completed_import(client, token, account_id, rows=1, salt=f"lotto{n}-", amount=f"-{20 + n}.00")

    result = await _events(client, token)
    assert result["total"] == 3
    assert len(result["items"]) == 3

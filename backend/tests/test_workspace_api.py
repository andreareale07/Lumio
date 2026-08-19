"""Test di `GET`/`PATCH /workspace` (sistema di valute — cambio della
`base_currency`) — stesso pattern di `test_auth.py`.
"""
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_get_workspace_returns_default_base_currency(client):
    token = await _register(client, "workspace-get@example.com")
    response = await client.get("/api/v1/workspace", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["base_currency"] == "EUR"
    assert response.json()["name"] == "Personale"


async def _fake_enqueue(workspace_id, user_id) -> str:
    return "fake-job-id"


async def test_patch_workspace_changes_base_currency(client, monkeypatch):
    monkeypatch.setattr("app.api.v1.workspace.enqueue_market_data_refresh", _fake_enqueue)
    token = await _register(client, "workspace-patch@example.com")
    response = await client.patch(
        "/api/v1/workspace", json={"base_currency": "usd"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["base_currency"] == "USD"  # normalizzato in maiuscolo

    get_response = await client.get("/api/v1/workspace", headers=_auth_headers(token))
    assert get_response.json()["base_currency"] == "USD"


async def test_patch_workspace_changes_default_analytics_currency(client, monkeypatch):
    """Regressione end-to-end: cambiare base_currency deve riflettersi
    immediatamente su resolve_currency (analytics), senza bisogno di
    ripassare `?currency=` esplicitamente."""
    monkeypatch.setattr("app.api.v1.workspace.enqueue_market_data_refresh", _fake_enqueue)
    token = await _register(client, "workspace-patch-analytics@example.com")
    await client.patch("/api/v1/workspace", json={"base_currency": "USD"}, headers=_auth_headers(token))

    summary = await client.get(
        "/api/v1/analytics/summary",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31"},
        headers=_auth_headers(token),
    )
    assert summary.json()["currency"] == "USD"


async def test_patch_workspace_rejects_unknown_currency_code(client):
    token = await _register(client, "workspace-patch-invalid@example.com")
    response = await client.patch(
        "/api/v1/workspace", json={"base_currency": "XXX"}, headers=_auth_headers(token)
    )
    assert response.status_code == 400


async def test_patch_workspace_triggers_fx_refresh_when_currency_changes(client, monkeypatch):
    """Regressione bug reale (segnalato dall'utente): `fx_rates` ha sempre
    e solo tassi VERSO la vecchia base_currency (es. USD->EUR, mai
    EUR->USD) — cambiando base_currency senza questo refresh immediato,
    ogni dato nella vecchia valuta sparirebbe da ogni totale (dashboard,
    investimenti, entrate) finche' non arriva il cron del giorno dopo."""
    calls = []

    async def fake_enqueue(workspace_id, user_id):
        calls.append((workspace_id, user_id))
        return "fake-job-id"

    monkeypatch.setattr("app.api.v1.workspace.enqueue_market_data_refresh", fake_enqueue)

    token = await _register(client, "workspace-patch-fx-refresh@example.com")
    response = await client.patch(
        "/api/v1/workspace", json={"base_currency": "USD"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert len(calls) == 1


async def test_patch_workspace_does_not_trigger_refresh_when_currency_unchanged(client, monkeypatch):
    calls = []

    async def fake_enqueue(workspace_id, user_id):
        calls.append((workspace_id, user_id))
        return "fake-job-id"

    monkeypatch.setattr("app.api.v1.workspace.enqueue_market_data_refresh", fake_enqueue)

    token = await _register(client, "workspace-patch-fx-refresh-noop@example.com")
    response = await client.patch(
        "/api/v1/workspace", json={"base_currency": "EUR"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert calls == []  # gia' EUR (default): nessun cambio, nessun refresh accodato


async def test_patch_workspace_does_not_enqueue_second_refresh_while_one_is_running(client, monkeypatch):
    from app.services.job_run_tracker import start_run

    calls = []

    async def fake_enqueue(workspace_id, user_id):
        calls.append((workspace_id, user_id))
        return "fake-job-id"

    monkeypatch.setattr("app.api.v1.workspace.enqueue_market_data_refresh", fake_enqueue)

    token = await _register(client, "workspace-patch-fx-refresh-running@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    import uuid as uuid_module

    workspace_id = uuid_module.UUID(me.json()["workspace_id"])
    user_id = uuid_module.UUID(me.json()["id"])
    await start_run(workspace_id, user_id, "market_data_refresh")

    response = await client.patch(
        "/api/v1/workspace", json={"base_currency": "USD"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert calls == []  # un refresh e' gia' in corso: nessun secondo job accodato

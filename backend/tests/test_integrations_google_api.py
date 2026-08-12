"""Test degli endpoint `/integrations/google/*` (milestone 10). Richiede
`GOOGLE_ENABLED=true` nel processo pytest (il router e' montato una sola
volta, all'import di `app.main` — vedi `app/api/v1/router.py`): eseguire
questo file con GOOGLE_ENABLED=true/GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/
GOOGLE_REDIRECT_URI/GOOGLE_PICKER_API_KEY valorizzati (anche fittizi, le
chiamate vere a Google sono sempre mockate con httpx_mock).
"""
import uuid
from urllib.parse import parse_qs, urlsplit

from httpx import AsyncClient

from app.services.job_run_tracker import start_run


async def _register(client: AsyncClient, email: str) -> tuple[str, uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    body = response.json()
    return body["access_token"], uuid.UUID(body["user"]["id"]), uuid.UUID(body["user"]["workspace_id"])


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _connect_google(client: AsyncClient, token: str, httpx_mock, email: str = "me@gmail.com") -> None:
    connect_resp = await client.get("/api/v1/integrations/google/connect", headers=_auth_headers(token))
    authorize_url = connect_resp.json()["authorize_url"]
    query = parse_qs(urlsplit(authorize_url).query)
    state = query["state"][0]

    httpx_mock.add_response(
        url="https://oauth2.googleapis.com/token",
        json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "drive.file"},
    )
    httpx_mock.add_response(url="https://openidconnect.googleapis.com/v1/userinfo", json={"email": email})
    httpx_mock.add_response(
        url="https://sheets.googleapis.com/v4/spreadsheets",
        json={"spreadsheetId": "sheet123", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/sheet123"},
    )
    callback_resp = await client.get(
        "/api/v1/integrations/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "connected=1" in callback_resp.headers["location"]


async def test_get_integration_returns_null_when_not_connected(client):
    token, _, _ = await _register(client, "google-none@example.com")
    response = await client.get("/api/v1/integrations/google", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() is None


async def test_connect_returns_google_authorize_url(client):
    """`/connect` ritorna l'URL invece di rispondere con un redirect diretto:
    l'endpoint richiede bearer token per costruire lo `state`, ma una
    navigazione reale del browser non porterebbe l'header Authorization —
    e' il frontend a navigare da solo su `authorize_url` (vedi
    `ConnectUrlOut`)."""
    token, _, _ = await _register(client, "google-connect@example.com")
    response = await client.get("/api/v1/integrations/google/connect", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["authorize_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth")


async def test_callback_creates_integration_with_spreadsheet_and_email(client, httpx_mock):
    token, _, _ = await _register(client, "google-callback@example.com")
    await _connect_google(client, token, httpx_mock, email="callback@gmail.com")

    status_resp = await client.get("/api/v1/integrations/google", headers=_auth_headers(token))
    body = status_resp.json()
    assert body["google_account_email"] == "callback@gmail.com"
    assert body["spreadsheet_url"].endswith("sheet123")
    assert body["drive_folder_name"] is None


async def test_callback_with_invalid_state_redirects_with_error(client):
    response = await client.get(
        "/api/v1/integrations/google/callback",
        params={"code": "auth-code", "state": "garbage"},
        follow_redirects=False,
    )
    assert "google_error=invalid_state" in response.headers["location"]


async def test_folder_endpoint_moves_file_and_updates_name(client, httpx_mock):
    token, _, _ = await _register(client, "google-folder@example.com")
    await _connect_google(client, token, httpx_mock)

    httpx_mock.add_response(json={"parents": ["root"]})  # GET parents attuali
    httpx_mock.add_response(json={})  # PATCH move

    response = await client.post(
        "/api/v1/integrations/google/folder",
        json={"folder_id": "folder-abc", "folder_name": "Finanze"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["drive_folder_name"] == "Finanze"


async def test_disconnect_removes_integration_even_if_revoke_fails(client, httpx_mock):
    token, _, _ = await _register(client, "google-disconnect@example.com")
    await _connect_google(client, token, httpx_mock)

    httpx_mock.add_response(url="https://oauth2.googleapis.com/revoke", status_code=500)

    response = await client.post("/api/v1/integrations/google/disconnect", headers=_auth_headers(token))
    assert response.status_code == 204

    status_resp = await client.get("/api/v1/integrations/google", headers=_auth_headers(token))
    assert status_resp.json() is None


async def test_export_requires_existing_integration(client):
    token, _, _ = await _register(client, "google-export-404@example.com")
    response = await client.post(
        "/api/v1/integrations/google/export",
        json={"date_from": "2026-05-01", "date_to": "2026-05-31"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


async def test_export_enqueues_job_and_is_idempotent_while_running(client, httpx_mock, monkeypatch):
    import app.api.v1.integrations_google as integrations_google_module

    calls = []

    async def fake_enqueue(workspace_id, user_id, options):
        calls.append((workspace_id, user_id, options))
        return "fake-export-job-id"

    monkeypatch.setattr(integrations_google_module, "enqueue_google_sheets_export", fake_enqueue)

    token, user_id, workspace_id = await _register(client, "google-export@example.com")
    await _connect_google(client, token, httpx_mock)

    response = await client.post(
        "/api/v1/integrations/google/export",
        json={"date_from": "2026-05-01", "date_to": "2026-05-31"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == "fake-export-job-id"
    assert len(calls) == 1

    # Doppio-click mentre un export e' gia' "running": nessun secondo job accodato.
    await start_run(workspace_id, user_id, "google_sheets_export")
    response2 = await client.post(
        "/api/v1/integrations/google/export",
        json={"date_from": "2026-05-01", "date_to": "2026-05-31"},
        headers=_auth_headers(token),
    )
    assert response2.status_code == 202
    assert len(calls) == 1


async def test_export_status_null_when_never_run(client, httpx_mock):
    token, _, _ = await _register(client, "google-export-status-null@example.com")
    await _connect_google(client, token, httpx_mock)
    response = await client.get("/api/v1/integrations/google/export-status", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() is None


async def test_picker_token_returns_access_token(client, httpx_mock):
    token, _, _ = await _register(client, "google-picker-token@example.com")
    await _connect_google(client, token, httpx_mock)

    response = await client.get("/api/v1/integrations/google/picker-token", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "at"
    assert body["expires_in_seconds"] > 0


async def test_picker_token_requires_existing_integration(client):
    token, _, _ = await _register(client, "google-picker-token-404@example.com")
    response = await client.get("/api/v1/integrations/google/picker-token", headers=_auth_headers(token))
    assert response.status_code == 404

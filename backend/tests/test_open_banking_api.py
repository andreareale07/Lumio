"""Endpoint `/open-banking/*` e sincronizzazione, con provider interamente
mockato (`httpx_mock` per le chiamate HTTP, un connettore finto per la sync) e
dati sintetici. Richiede `OPEN_BANKING_ENABLED=true` nel processo pytest (il
router e' montato una sola volta all'import di `app.main`, vedi
`app/api/v1/router.py`): lanciare questo file con la variabile impostata.
"""
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.redis import redis_client
from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.open_banking import BankConnection, BankConnectionAccount
from app.models.transaction import Transaction
from app.openbanking.base import NormalizedTransaction
from app.openbanking.errors import AuthorizationExpiredError, RateLimitedError
from app.services import bank_sync_service, open_banking_service

BASE = "https://api.enablebanking.com"
APP_ID = "app-id-synthetic-0001"
IBAN = "IT60X0542811101000000123456"


@pytest.fixture(autouse=True)
def _redirect_uri(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "open_banking_redirect_uri", "https://lumio.example/api/v1/open-banking/callback"
    )


@pytest.fixture(autouse=True)
async def _clean_sync_keys():
    async for key in redis_client.scan_iter(match="bank_sync:*"):
        await redis_client.delete(key)
    yield


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient, email: str) -> tuple[str, uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    body = response.json()
    return body["access_token"], uuid.UUID(body["user"]["id"]), uuid.UUID(body["user"]["workspace_id"])


async def _setup_credentials(client: AsyncClient, token: str) -> dict:
    created = await client.post("/api/v1/open-banking/credentials", headers=_h(token))
    assert created.status_code == 201
    updated = await client.put(
        "/api/v1/open-banking/credentials/application-id", json={"application_id": APP_ID}, headers=_h(token)
    )
    assert updated.status_code == 200
    return updated.json()


async def _link_bank(
    client: AsyncClient, token: str, httpx_mock, *, session_id: str = "sess-1", revoke_previous: str | None = None
) -> tuple[str, str]:
    """Percorre l'intero flusso start -> callback. Ritorna (state, location)."""
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={"aspsps": [{"name": "Banca Test", "country": "IT", "psu_types": ["personal"],
                          "maximum_consent_validity": 15552000}]},
    )
    httpx_mock.add_response(
        url=f"{BASE}/auth", method="POST", json={"url": "https://bank.example/auth", "authorization_id": "auth-1"}
    )
    start = await client.post(
        "/api/v1/open-banking/connections",
        json={"aspsp_name": "Banca Test", "aspsp_country": "IT"},
        headers=_h(token),
    )
    assert start.status_code == 200, start.text
    assert start.json()["authorize_url"] == "https://bank.example/auth"
    state = json.loads([r for r in httpx_mock.get_requests() if r.url.path == "/auth"][-1].content)["state"]

    httpx_mock.add_response(
        url=f"{BASE}/sessions",
        method="POST",
        json={
            "session_id": session_id,
            "access": {"valid_until": "2099-01-01T00:00:00Z"},
            "accounts": [{"uid": "acc-uid-1", "account_id": {"iban": IBAN}, "name": "Conto Test",
                          "currency": "EUR", "cash_account_type": "CACC"}],
        },
    )
    if revoke_previous:
        httpx_mock.add_response(url=f"{BASE}/sessions/{revoke_previous}", method="DELETE", status_code=204)
    callback = await client.get(
        "/api/v1/open-banking/callback", params={"code": "c", "state": state}, follow_redirects=False
    )
    return state, callback.headers["location"]


async def _connections(client: AsyncClient, token: str) -> list[dict]:
    response = await client.get("/api/v1/open-banking/connections", headers=_h(token))
    assert response.status_code == 200
    return response.json()


async def _enable_first_account(client: AsyncClient, token: str) -> tuple[str, str, str]:
    connection = (await _connections(client, token))[0]
    account = connection["accounts"][0]
    base = f"/api/v1/open-banking/connections/{connection['id']}/accounts/{account['id']}"
    mapped = await client.patch(base, json={"create_account": True}, headers=_h(token))
    assert mapped.status_code == 200, mapped.text
    enabled = await client.patch(base, json={"enabled": True}, headers=_h(token))
    assert enabled.status_code == 200
    return connection["id"], account["id"], enabled.json()["financial_account_id"]


# ---- credenziali ---------------------------------------------------------------


async def test_generate_credentials_returns_certificate_and_never_the_private_key(client):
    token, _, _ = await _register(client, "ob-cred@example.com")
    response = await client.post("/api/v1/open-banking/credentials", headers=_h(token))
    assert response.status_code == 201
    body = response.json()
    assert body["configured"] is False and body["application_id"] is None
    assert "BEGIN CERTIFICATE" in body["certificate_pem"]
    assert "PRIVATE KEY" not in response.text

    status_body = (await client.get("/api/v1/open-banking", headers=_h(token))).json()
    assert status_body["redirect_uri_configured"] is True
    assert "PRIVATE KEY" not in json.dumps(status_body)

    assert (await client.post("/api/v1/open-banking/credentials", headers=_h(token))).status_code == 409


async def test_private_key_is_stored_encrypted(client):
    token, user_id, _ = await _register(client, "ob-enc@example.com")
    await client.post("/api/v1/open-banking/credentials", headers=_h(token))
    async with rls_session(user_id) as db:
        stored = (await db.execute(text("SELECT private_key_encrypted FROM open_banking_credentials"))).scalar_one()
    assert "PRIVATE KEY" not in stored


async def test_invalid_application_id_is_rejected(client):
    token, _, _ = await _register(client, "ob-appid@example.com")
    await client.post("/api/v1/open-banking/credentials", headers=_h(token))
    response = await client.put(
        "/api/v1/open-banking/credentials/application-id", json={"application_id": "bad id!"}, headers=_h(token)
    )
    assert response.status_code == 422


async def test_endpoints_require_authentication(client):
    assert (await client.get("/api/v1/open-banking")).status_code == 401
    assert (await client.get("/api/v1/open-banking/connections")).status_code == 401


async def test_credentials_are_private_to_each_user(client):
    token_a, _, _ = await _register(client, "ob-a@example.com")
    token_b, _, _ = await _register(client, "ob-b@example.com")
    await _setup_credentials(client, token_a)
    assert (await client.get("/api/v1/open-banking", headers=_h(token_b))).json()["credential"] is None


# ---- istituti e collegamento -----------------------------------------------------


async def test_institutions_requires_credentials_and_filters_business_only_banks(client, httpx_mock):
    token, _, _ = await _register(client, "ob-inst@example.com")
    assert (await client.get("/api/v1/open-banking/institutions?country=IT", headers=_h(token))).status_code == 404

    await _setup_credentials(client, token)
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={"aspsps": [
            {"name": "Banca Privati", "country": "IT", "psu_types": ["personal", "business"]},
            {"name": "Banca Solo Aziende", "country": "IT", "psu_types": ["business"]},
        ]},
    )
    response = await client.get("/api/v1/open-banking/institutions?country=IT", headers=_h(token))
    assert [i["name"] for i in response.json()] == ["Banca Privati"]

    assert (await client.get("/api/v1/open-banking/institutions?country=ITA", headers=_h(token))).status_code == 422


async def test_start_requires_redirect_uri_and_configured_app(client, monkeypatch):
    token, _, _ = await _register(client, "ob-start@example.com")
    body = {"aspsp_name": "Banca Test", "aspsp_country": "IT"}
    assert (await client.post("/api/v1/open-banking/connections", json=body, headers=_h(token))).status_code == 404

    await client.post("/api/v1/open-banking/credentials", headers=_h(token))
    response = await client.post("/api/v1/open-banking/connections", json=body, headers=_h(token))
    assert response.status_code == 400  # application ID ancora mancante

    monkeypatch.setattr(get_settings(), "open_banking_redirect_uri", "")
    response = await client.post("/api/v1/open-banking/connections", json=body, headers=_h(token))
    assert response.status_code == 503


async def test_business_psu_type_is_not_accepted(client):
    token, _, _ = await _register(client, "ob-biz@example.com")
    response = await client.post(
        "/api/v1/open-banking/connections",
        json={"aspsp_name": "Banca Test", "aspsp_country": "IT", "psu_type": "business"},
        headers=_h(token),
    )
    assert response.status_code == 422


async def test_unknown_bank_is_404(client, httpx_mock):
    token, _, _ = await _register(client, "ob-unk@example.com")
    await _setup_credentials(client, token)
    httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", json={"aspsps": []})
    response = await client.post(
        "/api/v1/open-banking/connections",
        json={"aspsp_name": "Banca Inesistente", "aspsp_country": "IT"},
        headers=_h(token),
    )
    assert response.status_code == 404


async def test_full_authorization_flow_creates_active_connection_with_accounts(client, httpx_mock):
    token, user_id, _ = await _register(client, "ob-flow@example.com")
    await _setup_credentials(client, token)
    _state, location = await _link_bank(client, token, httpx_mock)

    assert location.startswith("/settings/bank-connections?connected=")
    connections = await _connections(client, token)
    assert len(connections) == 1
    connection = connections[0]
    assert connection["status"] == "active"
    assert connection["aspsp_name"] == "Banca Test"
    assert connection["days_until_expiry"] > 30 and connection["expiring_soon"] is False
    account = connection["accounts"][0]
    assert account["enabled"] is False and account["financial_account_id"] is None
    assert account["iban_masked"] == "IT60••••3456"
    # Nessun token/sessione nelle risposte al browser.
    assert "sess-1" not in json.dumps(connections)

    async with rls_session(user_id) as db:
        stored = (await db.scalars(select(BankConnection))).one()
        assert stored.session_id_encrypted and "sess-1" not in stored.session_id_encrypted
        assert stored.state_nonce_hash is None  # nonce consumato

    start_body = json.loads([r for r in httpx_mock.get_requests() if r.url.path == "/auth"][-1].content)
    assert start_body["redirect_url"] == "https://lumio.example/api/v1/open-banking/callback"
    assert start_body["psu_type"] == "personal"


async def test_callback_state_is_single_use(client, httpx_mock):
    token, _, _ = await _register(client, "ob-replay@example.com")
    await _setup_credentials(client, token)
    state, _ = await _link_bank(client, token, httpx_mock)
    replay = await client.get(
        "/api/v1/open-banking/callback", params={"code": "c2", "state": state}, follow_redirects=False
    )
    assert replay.headers["location"].endswith("error=invalid_state")


async def test_callback_rejects_missing_or_forged_state(client):
    for params in ({}, {"code": "c"}, {"code": "c", "state": "forged"}):
        response = await client.get("/api/v1/open-banking/callback", params=params, follow_redirects=False)
        assert response.headers["location"].endswith("error=invalid_state")


async def test_callback_with_provider_error_marks_connection_failed(client, httpx_mock):
    token, user_id, _ = await _register(client, "ob-denied@example.com")
    await _setup_credentials(client, token)
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={"aspsps": [{"name": "Banca Test", "country": "IT", "psu_types": ["personal"]}]},
    )
    httpx_mock.add_response(url=f"{BASE}/auth", method="POST", json={"url": "https://bank.example/a"})
    await client.post(
        "/api/v1/open-banking/connections",
        json={"aspsp_name": "Banca Test", "aspsp_country": "IT"},
        headers=_h(token),
    )
    state = json.loads([r for r in httpx_mock.get_requests() if r.url.path == "/auth"][-1].content)["state"]
    response = await client.get(
        "/api/v1/open-banking/callback", params={"error": "access_denied", "state": state}, follow_redirects=False
    )
    assert response.headers["location"].endswith("error=authorization_denied")
    async with rls_session(user_id) as db:
        stored = (await db.scalars(select(BankConnection))).one()
    assert stored.status == "error" and stored.last_error == "authorization_denied"
    assert await _connections(client, token) == []  # le connessioni non completate non si elencano


async def test_session_exchange_failure_is_reported_without_leaking_details(client, httpx_mock):
    token, user_id, _ = await _register(client, "ob-fail@example.com")
    await _setup_credentials(client, token)
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={"aspsps": [{"name": "Banca Test", "country": "IT", "psu_types": ["personal"]}]},
    )
    httpx_mock.add_response(url=f"{BASE}/auth", method="POST", json={"url": "https://bank.example/a"})
    await client.post(
        "/api/v1/open-banking/connections",
        json={"aspsp_name": "Banca Test", "aspsp_country": "IT"},
        headers=_h(token),
    )
    state = json.loads([r for r in httpx_mock.get_requests() if r.url.path == "/auth"][-1].content)["state"]
    httpx_mock.add_response(
        url=f"{BASE}/sessions", method="POST", status_code=400, json={"error": "EXPIRED_AUTHORIZATION_CODE"}
    )
    response = await client.get(
        "/api/v1/open-banking/callback", params={"code": "old", "state": state}, follow_redirects=False
    )
    assert response.headers["location"].endswith("error=authorization_failed")
    async with rls_session(user_id) as db:
        stored = (await db.scalars(select(BankConnection))).one()
    assert stored.status == "error" and stored.session_id_encrypted is None


async def test_renewal_inherits_mapping_and_revokes_previous_session(client, httpx_mock):
    token, user_id, _ = await _register(client, "ob-renew@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock, session_id="sess-1")
    _connection_id, _account_id, financial_account_id = await _enable_first_account(client, token)

    async with rls_session(user_id) as db:
        account = (await db.scalars(select(BankConnectionAccount))).one()
        account.last_booked_date = date(2026, 3, 1)
        account.transactions_imported = 5
        await db.commit()

    await _link_bank(client, token, httpx_mock, session_id="sess-2", revoke_previous="sess-1")

    connections = await _connections(client, token)
    assert len(connections) == 1  # la precedente e' stata ritirata
    account = connections[0]["accounts"][0]
    assert account["enabled"] is True
    assert account["financial_account_id"] == financial_account_id
    assert account["transactions_imported"] == 5
    async with rls_session(user_id) as db:
        stored = (await db.scalars(select(BankConnectionAccount))).one()
    assert stored.last_booked_date == date(2026, 3, 1)


# ---- abbinamento conti -------------------------------------------------------------


async def test_account_must_be_mapped_before_being_enabled(client, httpx_mock):
    token, _, _ = await _register(client, "ob-map@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection = (await _connections(client, token))[0]
    path = f"/api/v1/open-banking/connections/{connection['id']}/accounts/{connection['accounts'][0]['id']}"

    assert (await client.patch(path, json={"enabled": True}, headers=_h(token))).status_code == 422
    both = {"create_account": True, "financial_account_id": str(uuid.uuid4())}
    assert (await client.patch(path, json=both, headers=_h(token))).status_code == 422
    unknown = {"financial_account_id": str(uuid.uuid4())}
    assert (await client.patch(path, json=unknown, headers=_h(token))).status_code == 404


async def test_create_account_builds_a_lumio_account_from_bank_data(client, httpx_mock):
    token, _, _ = await _register(client, "ob-create@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    _c, _a, financial_account_id = await _enable_first_account(client, token)

    accounts = (await client.get("/api/v1/accounts", headers=_h(token))).json()
    created = next(a for a in accounts if a["id"] == financial_account_id)
    assert created["iban"] == IBAN
    assert created["currency"] == "EUR"
    assert created["account_type"] == "checking"
    assert created["name"].startswith("Banca Test")


async def test_cannot_map_to_an_account_of_another_workspace(client, httpx_mock):
    token_a, _, _ = await _register(client, "ob-x-a@example.com")
    token_b, _, _ = await _register(client, "ob-x-b@example.com")
    foreign = (
        await client.post(
            "/api/v1/accounts",
            json={"name": "Altro", "account_type": "checking", "currency": "EUR"},
            headers=_h(token_b),
        )
    ).json()["id"]
    await _setup_credentials(client, token_a)
    await _link_bank(client, token_a, httpx_mock)
    connection = (await _connections(client, token_a))[0]
    path = f"/api/v1/open-banking/connections/{connection['id']}/accounts/{connection['accounts'][0]['id']}"
    assert (
        await client.patch(path, json={"financial_account_id": foreign}, headers=_h(token_a))
    ).status_code == 404


async def test_another_user_cannot_see_or_touch_the_connection(client, httpx_mock):
    token_a, _, _ = await _register(client, "ob-own-a@example.com")
    token_b, _, _ = await _register(client, "ob-own-b@example.com")
    await _setup_credentials(client, token_a)
    await _link_bank(client, token_a, httpx_mock)
    connection = (await _connections(client, token_a))[0]

    assert await _connections(client, token_b) == []
    assert (
        await client.delete(f"/api/v1/open-banking/connections/{connection['id']}", headers=_h(token_b))
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/open-banking/connections/{connection['id']}/sync", headers=_h(token_b))
    ).status_code == 404


# ---- sync manuale (endpoint) ---------------------------------------------------------


async def test_manual_sync_endpoint_queues_job_with_user_presence(client, httpx_mock, monkeypatch):
    token, _, _ = await _register(client, "ob-sync-api@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _a, _f = await _enable_first_account(client, token)

    queued = AsyncMock(return_value="job")
    monkeypatch.setattr("app.api.v1.open_banking.enqueue_bank_sync", queued)
    response = await client.post(
        f"/api/v1/open-banking/connections/{connection_id}/sync",
        headers={**_h(token), "X-Forwarded-For": "203.0.113.9, 10.0.0.1", "User-Agent": "TestUA/1"},
    )
    assert response.status_code == 202
    kwargs = queued.await_args.kwargs
    # L'IP e' quello del peer (risolto da uvicorn dietro i proxy fidati), MAI
    # l'header inviato dal client: vedi test_open_banking_security.py.
    assert kwargs["psu_ip"] != "203.0.113.9" and kwargs["psu_user_agent"] == "TestUA/1"

    await redis_client.set(f"bank_sync:lock:{connection_id}", "1", ex=60)
    again = await client.post(f"/api/v1/open-banking/connections/{connection_id}/sync", headers=_h(token))
    assert again.status_code == 409
    assert (await _connections(client, token))[0]["sync_running"] is True


async def test_manual_sync_requires_an_enabled_mapped_account(client, httpx_mock):
    token, _, _ = await _register(client, "ob-sync-none@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection = (await _connections(client, token))[0]
    response = await client.post(f"/api/v1/open-banking/connections/{connection['id']}/sync", headers=_h(token))
    assert response.status_code == 409


async def test_expired_authorization_blocks_manual_sync_and_is_reported(client, httpx_mock):
    token, user_id, _ = await _register(client, "ob-exp-api@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _a, _f = await _enable_first_account(client, token)
    async with rls_session(user_id) as db:
        stored = await db.get(BankConnection, uuid.UUID(connection_id))
        stored.valid_until = datetime.now(UTC) - timedelta(days=1)
        await db.commit()

    assert (await _connections(client, token))[0]["status"] == "expired"
    response = await client.post(f"/api/v1/open-banking/connections/{connection_id}/sync", headers=_h(token))
    assert response.status_code == 409


async def test_expiring_soon_flag(client, httpx_mock):
    token, user_id, _ = await _register(client, "ob-soon@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection = (await _connections(client, token))[0]
    async with rls_session(user_id) as db:
        stored = await db.get(BankConnection, uuid.UUID(connection["id"]))
        stored.valid_until = datetime.now(UTC) + timedelta(days=3, hours=1)
        await db.commit()
    refreshed = (await _connections(client, token))[0]
    assert refreshed["status"] == "active" and refreshed["expiring_soon"] is True


# ---- scollegamento --------------------------------------------------------------------


async def test_disconnect_revokes_session_and_keeps_imported_transactions(client, httpx_mock, monkeypatch):
    token, user_id, _ = await _register(client, "ob-disc@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _a, financial_account_id = await _enable_first_account(client, token)

    fake = _FakeConnector([[_ntx("e1", "-10.00", date(2026, 3, 1), "Caffe")]])
    monkeypatch.setattr(open_banking_service, "build_connector", lambda credential: fake)
    summary = await bank_sync_service.sync_connection(uuid.UUID(connection_id), user_id)
    assert summary.imported == 1

    response = await client.delete(f"/api/v1/open-banking/connections/{connection_id}", headers=_h(token))
    assert response.status_code == 200
    assert response.json() == {"deleted_transactions": 0, "revoked_at_bank": True}
    assert fake.revoked == ["sess-1"]
    assert await _connections(client, token) == []
    async with rls_session(user_id) as db:
        remaining = (await db.scalars(select(Transaction).where(
            Transaction.financial_account_id == uuid.UUID(financial_account_id)))).all()
    assert len(remaining) == 1


async def test_disconnect_succeeds_even_if_provider_revocation_fails(client, httpx_mock):
    token, _, _ = await _register(client, "ob-disc2@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection = (await _connections(client, token))[0]
    for _ in range(3):
        httpx_mock.add_response(url=f"{BASE}/sessions/sess-1", method="DELETE", status_code=503, json={})
    response = await client.delete(f"/api/v1/open-banking/connections/{connection['id']}", headers=_h(token))
    assert response.status_code == 200
    assert response.json()["revoked_at_bank"] is False
    assert await _connections(client, token) == []


async def test_disconnect_with_delete_data_removes_only_open_banking_movements(client, httpx_mock, monkeypatch):
    token, user_id, workspace_id = await _register(client, "ob-deldata@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _a, financial_account_id = await _enable_first_account(client, token)
    fake = _FakeConnector([[_ntx("e1", "-10.00", date(2026, 3, 1), "Caffe"), _ntx("e2", "5.00", date(2026, 3, 2), "Rimborso")]])
    _use(monkeypatch, fake)
    assert (await bank_sync_service.sync_connection(uuid.UUID(connection_id), user_id)).imported == 2

    # Un movimento inserito a mano e uno arrivato da un import PDF/CSV sullo STESSO conto Lumio: devono restare.
    async with rls_session(user_id) as db:
        pdf_import = Import(
            workspace_id=workspace_id,
            financial_account_id=uuid.UUID(financial_account_id),
            created_by_user_id=user_id,
            file_type="csv",
            status="completed",
            filename="estratto.csv",
            file_hash="b" * 64,
            file_size=10,
        )
        db.add(pdf_import)
        await db.flush()
        for import_id in (None, pdf_import.id):
            db.add(
                Transaction(
                    workspace_id=workspace_id,
                    financial_account_id=uuid.UUID(financial_account_id),
                    import_id=import_id,
                    transaction_date=date(2026, 3, 3),
                    description_raw=f"altro {import_id}",
                    amount=Decimal("-1.00"),
                    currency="EUR",
                    direction="debit",
                    transaction_type="expense",
                    dedup_fingerprint=("c" if import_id else "d") * 64,
                )
            )
        await db.commit()

    response = await client.delete(
        f"/api/v1/open-banking/connections/{connection_id}?delete_data=true", headers=_h(token)
    )
    assert response.status_code == 200
    assert response.json()["deleted_transactions"] == 2
    assert fake.revoked == ["sess-1"]
    async with rls_session(user_id) as db:
        remaining = (await db.scalars(select(Transaction))).all()
        assert sorted(t.description_raw.split()[0] for t in remaining) == ["altro", "altro"]
        assert [i.file_type for i in (await db.scalars(select(Import))).all()] == ["csv"]
        events = (
            await db.execute(text("SELECT metadata FROM audit_log WHERE event_type = 'BANK_DISCONNECTED'"))
        ).scalars().all()
    assert events == [{"deleted_transactions_count": 2}]


async def test_delete_data_is_refused_while_an_import_is_running_and_nothing_is_revoked(client, httpx_mock, monkeypatch):
    token, user_id, workspace_id = await _register(client, "ob-delbusy@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _a, financial_account_id = await _enable_first_account(client, token)
    async with rls_session(user_id) as db:
        db.add(
            Import(
                workspace_id=workspace_id,
                financial_account_id=uuid.UUID(financial_account_id),
                created_by_user_id=user_id,
                file_type="open_banking",
                status="parsing",
                filename="Open Banking - Banca Test",
                file_hash="e" * 64,
                file_size=0,
            )
        )
        await db.commit()
    fake = _FakeConnector([])
    _use(monkeypatch, fake)

    response = await client.delete(
        f"/api/v1/open-banking/connections/{connection_id}?delete_data=true", headers=_h(token)
    )
    assert response.status_code == 409
    assert fake.revoked == []
    assert len(await _connections(client, token)) == 1


async def test_delete_credentials_removes_connections_and_audits(client, httpx_mock):
    token, user_id, _ = await _register(client, "ob-delcred@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/sessions/sess-1", method="DELETE", status_code=204)
    assert (await client.delete("/api/v1/open-banking/credentials", headers=_h(token))).status_code == 204
    assert (await client.get("/api/v1/open-banking", headers=_h(token))).json()["credential"] is None
    assert await _connections(client, token) == []
    async with rls_session(user_id) as db:
        events = (await db.execute(text("SELECT event_type FROM audit_log ORDER BY created_at"))).scalars().all()
    assert "BANK_CONNECTED" in events and "BANK_DISCONNECTED" in events


# ---- sincronizzazione (servizio) ----------------------------------------------------------


def _ntx(
    external_id: str | None,
    amount: str,
    booking: date,
    description: str,
    *,
    counterparty_name: str | None = None,
    counterparty_iban: str | None = None,
) -> NormalizedTransaction:
    return NormalizedTransaction(
        external_id=external_id,
        status="booked",
        amount=Decimal(amount),
        currency="EUR",
        transaction_date=booking,
        booking_date=booking,
        value_date=booking,
        description=description,
        counterparty_name=counterparty_name,
        counterparty_iban=counterparty_iban,
        balance_after=None,
        reference=None,
        bank_transaction_code="Pagamento POS",
        raw={},
    )


class _FakeConnector:
    provider = "enable_banking"

    def __init__(self, batches):
        self.batches = list(batches)
        self.calls: list[dict] = []
        self.error: Exception | None = None
        self.revoked: list[str] = []

    async def revoke(self, session_id):
        self.revoked.append(session_id)

    async def get_transactions(self, uid, *, date_from=None, date_to=None, longest=False, psu=None, stats=None):
        self.calls.append({"uid": uid, "date_from": date_from, "longest": longest, "psu": psu})
        if self.error is not None:
            raise self.error
        return self.batches.pop(0) if self.batches else []


async def _linked_and_enabled(client, httpx_mock, email: str):
    token, user_id, workspace_id = await _register(client, email)
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, account_id, financial_account_id = await _enable_first_account(client, token)
    return token, user_id, workspace_id, uuid.UUID(connection_id), uuid.UUID(account_id), uuid.UUID(financial_account_id)


def _use(monkeypatch, fake):
    monkeypatch.setattr(open_banking_service, "build_connector", lambda credential: fake)


async def test_first_sync_imports_everything_with_signed_amounts_and_external_ids(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, fin_id = await _linked_and_enabled(client, httpx_mock, "ob-s1@example.com")
    fake = _FakeConnector([[
        _ntx("e1", "-12.50", date(2026, 3, 1), "Caffe", counterparty_name="Bar Roma"),
        _ntx("e2", "1500.00", date(2026, 3, 2), "Stipendio marzo"),
    ]])
    _use(monkeypatch, fake)

    summary = await bank_sync_service.sync_connection(connection_id, user_id)

    assert summary.error_code is None and summary.imported == 2 and summary.accounts_synced == 1
    assert fake.calls[0]["longest"] is True and fake.calls[0]["date_from"] is None
    async with rls_session(user_id) as db:
        transactions = {t.external_id: t for t in (await db.scalars(select(Transaction))).all()}
        assert transactions["e1"].amount == Decimal("-12.50") and transactions["e1"].direction == "debit"
        assert transactions["e1"].transaction_type == "expense" and transactions["e1"].merchant == "Bar Roma"
        assert transactions["e2"].amount == Decimal("1500.00") and transactions["e2"].transaction_type == "income"
        assert transactions["e1"].financial_account_id == fin_id
        imports = (await db.scalars(select(Import))).all()
        assert [(i.file_type, i.status, i.transactions_imported) for i in imports] == [("open_banking", "completed", 2)]
        stored = await db.get(BankConnectionAccount, account_id)
        assert stored.last_booked_date == date(2026, 3, 2) and stored.transactions_imported == 2
        connection = await db.get(BankConnection, connection_id)
        assert connection.last_sync_at is not None and connection.last_error is None


async def test_sync_is_idempotent_and_only_new_rows_are_added(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "ob-s2@example.com")
    first = [_ntx("e1", "-5.00", date(2026, 3, 1), "A"), _ntx("e2", "-6.00", date(2026, 3, 2), "B")]
    fake = _FakeConnector([first, first, first + [_ntx("e3", "-7.00", date(2026, 3, 10), "C")]])
    _use(monkeypatch, fake)

    assert (await bank_sync_service.sync_connection(connection_id, user_id)).imported == 2
    second = await bank_sync_service.sync_connection(connection_id, user_id)
    assert second.imported == 0 and second.duplicates == 2
    third = await bank_sync_service.sync_connection(connection_id, user_id)
    assert third.imported == 1

    async with rls_session(user_id) as db:
        assert len((await db.scalars(select(Transaction))).all()) == 3
        # Il secondo giro non ha creato un Import vuoto.
        assert len((await db.scalars(select(Import))).all()) == 2

    # Dopo il primo giro la sync riparte con la finestra di riconciliazione.
    assert fake.calls[1]["longest"] is False
    assert fake.calls[1]["date_from"] == date(2026, 3, 2) - timedelta(days=30)


async def test_rows_without_external_id_fall_back_to_fingerprint_dedup(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s3@example.com")
    row = _ntx(None, "-9.99", date(2026, 3, 5), "Abbonamento")
    fake = _FakeConnector([[row], [row]])
    _use(monkeypatch, fake)

    assert (await bank_sync_service.sync_connection(connection_id, user_id)).imported == 1
    second = await bank_sync_service.sync_connection(connection_id, user_id)
    assert second.imported == 0
    async with rls_session(user_id) as db:
        assert len((await db.scalars(select(Transaction))).all()) == 1


async def test_duplicates_within_the_same_batch_are_collapsed(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s4@example.com")
    _use(monkeypatch, _FakeConnector([[_ntx("dup", "-1.00", date(2026, 3, 1), "X"),
                                       _ntx("dup", "-1.00", date(2026, 3, 1), "X")]]))
    summary = await bank_sync_service.sync_connection(connection_id, user_id)
    assert summary.imported == 1 and summary.duplicates == 1


async def test_expired_authorization_marks_connection_expired(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s5@example.com")
    fake = _FakeConnector([])
    fake.error = AuthorizationExpiredError("scaduta", code="EXPIRED_SESSION", http_status=401)
    _use(monkeypatch, fake)

    summary = await bank_sync_service.sync_connection(connection_id, user_id)
    assert summary.error_code == "authorization_expired"
    async with rls_session(user_id) as db:
        connection = await db.get(BankConnection, connection_id)
    assert connection.status == "expired" and connection.last_error == "authorization_expired"


async def test_sync_does_not_call_the_bank_when_consent_is_past_validity(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s6@example.com")
    async with rls_session(user_id) as db:
        connection = await db.get(BankConnection, connection_id)
        connection.valid_until = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    fake = _FakeConnector([[_ntx("e1", "-1.00", date(2026, 3, 1), "X")]])
    _use(monkeypatch, fake)

    summary = await bank_sync_service.sync_connection(connection_id, user_id)
    assert summary.error_code == "authorization_expired" and fake.calls == []
    async with rls_session(user_id) as db:
        assert (await db.get(BankConnection, connection_id)).status == "expired"


async def test_rate_limit_is_recorded_without_expiring_the_connection(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s7@example.com")
    fake = _FakeConnector([])
    fake.error = RateLimitedError("limite", http_status=429)
    _use(monkeypatch, fake)

    summary = await bank_sync_service.sync_connection(connection_id, user_id)
    assert summary.error_code == "rate_limited"
    async with rls_session(user_id) as db:
        connection = await db.get(BankConnection, connection_id)
    assert connection.status == "active" and connection.last_error == "rate_limited"
    assert connection.last_sync_at is None  # una sync fallita non conta come riuscita


async def test_successful_sync_clears_previous_error(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s8@example.com")
    fake = _FakeConnector([[]])
    fake.error = RateLimitedError("limite", http_status=429)
    _use(monkeypatch, fake)
    await bank_sync_service.sync_connection(connection_id, user_id)
    fake.error = None
    await bank_sync_service.sync_connection(connection_id, user_id)
    async with rls_session(user_id) as db:
        assert (await db.get(BankConnection, connection_id)).last_error is None


async def test_concurrent_sync_is_skipped_by_lock(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s9@example.com")
    fake = _FakeConnector([[_ntx("e1", "-1.00", date(2026, 3, 1), "X")]])
    _use(monkeypatch, fake)
    await redis_client.set(f"bank_sync:lock:{connection_id}", "1", ex=60)

    summary = await bank_sync_service.sync_connection(connection_id, user_id)
    assert summary.skipped is True and fake.calls == []
    # Il lock viene rilasciato a fine sync (non quello altrui, che scade da solo).
    await redis_client.delete(f"bank_sync:lock:{connection_id}")
    assert (await bank_sync_service.sync_connection(connection_id, user_id)).imported == 1
    assert await bank_sync_service.is_sync_running(connection_id) is False


async def test_scheduled_sync_respects_interval_but_manual_does_not(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s10@example.com")
    fake = _FakeConnector([[], [], []])
    _use(monkeypatch, fake)

    first = await bank_sync_service.sync_connection(connection_id, user_id, scheduled=True)
    again = await bank_sync_service.sync_connection(connection_id, user_id, scheduled=True)
    manual = await bank_sync_service.sync_connection(connection_id, user_id)
    assert first.skipped is False and again.skipped is True and manual.skipped is False
    assert len(fake.calls) == 2


async def test_failed_scheduled_sync_backs_off_longer_after_rate_limit(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s11@example.com")
    fake = _FakeConnector([])
    fake.error = RateLimitedError("limite", http_status=429)
    _use(monkeypatch, fake)
    await bank_sync_service.sync_connection(connection_id, user_id, scheduled=True)
    ttl = await redis_client.ttl(f"bank_sync:attempt:{connection_id}")
    assert ttl > bank_sync_service.effective_interval_seconds()


async def test_manual_sync_passes_user_presence_to_the_connector(client, httpx_mock, monkeypatch):
    from app.openbanking.base import PsuContext

    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s12@example.com")
    fake = _FakeConnector([[]])
    _use(monkeypatch, fake)
    psu = PsuContext(ip_address="203.0.113.5", user_agent="UA")
    await bank_sync_service.sync_connection(connection_id, user_id, psu=psu)
    assert fake.calls[0]["psu"] == psu


async def test_only_enabled_and_mapped_accounts_are_synced(client, httpx_mock, monkeypatch):
    token, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "ob-s13@example.com")
    connection = (await _connections(client, token))[0]
    path = f"/api/v1/open-banking/connections/{connection['id']}/accounts/{connection['accounts'][0]['id']}"
    await client.patch(path, json={"enabled": False}, headers=_h(token))
    fake = _FakeConnector([[_ntx("e1", "-1.00", date(2026, 3, 1), "X")]])
    _use(monkeypatch, fake)

    summary = await bank_sync_service.sync_connection(connection_id, user_id)
    assert fake.calls == [] and summary.imported == 0


async def test_internal_transfer_between_own_accounts_is_not_expense(client, httpx_mock, monkeypatch):
    token, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s14@example.com")
    other_iban = "IT28W8000000292100645211208"
    await client.post(
        "/api/v1/accounts",
        json={"name": "Risparmio", "account_type": "savings", "currency": "EUR", "iban": other_iban},
        headers=_h(token),
    )
    fake = _FakeConnector([[_ntx("t1", "-200.00", date(2026, 3, 3), "Giroconto", counterparty_iban=other_iban)]])
    _use(monkeypatch, fake)
    await bank_sync_service.sync_connection(connection_id, user_id)
    async with rls_session(user_id) as db:
        transaction = (await db.scalars(select(Transaction))).one()
    assert transaction.transaction_type == "transfer"


async def test_description_raw_is_stored_untouched(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "ob-s15@example.com")
    raw_text = "PAGAMENTO   POS  0012\nNEGOZIO  X"
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-3.00", date(2026, 3, 1), raw_text)]]))
    await bank_sync_service.sync_connection(connection_id, user_id)
    async with rls_session(user_id) as db:
        transaction = (await db.scalars(select(Transaction))).one()
    assert transaction.description_raw == raw_text
    assert transaction.description_normalized == "PAGAMENTO POS 0012 NEGOZIO X"


async def test_external_id_index_exists_and_is_partial():
    async with async_session_factory() as session:
        definition = (
            await session.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_transactions_workspace_account_external_id'")
            )
        ).scalar_one()
    assert "WHERE (external_id IS NOT NULL)" in definition and "UNIQUE" not in definition

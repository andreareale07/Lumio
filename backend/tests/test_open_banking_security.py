"""Correzioni dell'analisi di sicurezza Open Banking (2026-11-07): ogni test
dimostra una falla trovata nell'analisi. Provider interamente mockato, dati
sintetici. Richiede `OPEN_BANKING_ENABLED=true` (vedi test_open_banking_api.py)."""
import asyncio
import json
import logging
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.core.client_info import clean_user_agent, client_ip
from app.core.config import get_settings
from app.core.logging import RedactAccessLogFilter, redact_query_secrets
from app.core.redis import redis_client
from app.db.rls import rls_session
from app.openbanking.base import ConnectionSession, ProviderAccount
from app.openbanking.enable_banking import EnableBankingConnector
from app.openbanking.errors import OpenBankingError
from app.openbanking.urls import safe_provider_url
from app.services import bank_sync_service
from tests.test_open_banking_api import (
    BASE,
    IBAN,
    _connections,
    _enable_first_account,
    _h,
    _link_bank,
    _register,
    _setup_credentials,
)


@pytest.fixture(autouse=True)
def _redirect_uri(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "open_banking_redirect_uri", "https://lumio.example/api/v1/open-banking/callback"
    )


@pytest.fixture(autouse=True)
async def _clean_redis_keys():
    async def wipe():
        for pattern in ("bank_sync:*", "LIMITER*"):
            async for key in redis_client.scan_iter(match=pattern):
                await redis_client.delete(key)

    await wipe()
    yield
    await wipe()


async def _start(client, token, httpx_mock, url="https://bank.example/auth"):
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={"aspsps": [{"name": "Banca Test", "country": "IT", "psu_types": ["personal"]}]},
    )
    httpx_mock.add_response(url=f"{BASE}/auth", method="POST", json={"url": url, "authorization_id": "a"})
    response = await client.post(
        "/api/v1/open-banking/connections",
        json={"aspsp_name": "Banca Test", "aspsp_country": "IT"},
        headers=_h(token),
    )
    state = json.loads([r for r in httpx_mock.get_requests() if r.url.path == "/auth"][-1].content)["state"]
    return response, state


# ---- A2: URL del provider -------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,x",
        "http://bank.example/a",
        "https://u:p@bank.example/",
        "//x.example",
        "",
        None,
        "https://a b/",
    ],
)
def test_unsafe_provider_urls_are_rejected(url):
    assert safe_provider_url(url) is None


def test_https_provider_url_is_accepted():
    assert safe_provider_url("https://auth.example/start?x=1") == "https://auth.example/start?x=1"


async def test_javascript_authorize_url_from_provider_is_refused(client, httpx_mock):
    token, _, _ = await _register(client, "sec-js@example.com")
    await _setup_credentials(client, token)
    response, _ = await _start(client, token, httpx_mock, url="javascript:alert(document.domain)")
    assert response.status_code == 502
    assert "javascript" not in response.text
    # Nessuna connessione resta dopo il rifiuto.
    assert await _connections(client, token) == []


async def test_non_https_logo_is_dropped_from_institutions(client, httpx_mock):
    token, _, _ = await _register(client, "sec-logo@example.com")
    await _setup_credentials(client, token)
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={
            "aspsps": [
                {"name": "A", "country": "IT", "logo": "http://tracker.evil/p.png"},
                {"name": "B", "country": "IT", "logo": "https://cdn.example/b.png"},
            ]
        },
    )
    body = (await client.get("/api/v1/open-banking/institutions?country=IT", headers=_h(token))).json()
    by_name = {i["name"]: i["logo_url"] for i in body}
    assert by_name["A"] is None
    # Il browser riceve un percorso locale (proxy), mai l'indirizzo del provider.
    assert by_name["B"].startswith("/api/v1/open-banking/logos/") and "cdn.example" not in by_name["B"]


async def test_provider_identifiers_with_path_tricks_are_rejected():
    connector = EnableBankingConnector(application_id="app-id-synthetic-0001", private_key_pem="x")
    with pytest.raises(OpenBankingError):
        await connector.get_balances("../../sessions/abc")
    with pytest.raises(OpenBankingError):
        await connector.revoke("a/b?x=1")


# ---- M1: nonce monouso anche in concorrenza ----------------------------------------


async def test_concurrent_callbacks_consume_the_state_only_once(client, httpx_mock, monkeypatch):
    token, _, _ = await _register(client, "sec-race@example.com")
    await _setup_credentials(client, token)
    _, state = await _start(client, token, httpx_mock)
    calls: list[str] = []

    async def slow_complete(self, code):
        calls.append(code)
        await asyncio.sleep(0.4)
        return ConnectionSession(
            session_id="sess-race",
            accounts=[
                ProviderAccount(
                    uid="u1", iban=IBAN, name="n", product=None, currency="EUR", cash_account_type="CACC"
                )
            ],
            valid_until=None,
        )

    monkeypatch.setattr(EnableBankingConnector, "complete_authorization", slow_complete)
    responses = await asyncio.gather(
        *[
            client.get("/api/v1/open-banking/callback", params={"code": "c", "state": state}, follow_redirects=False)
            for _ in range(3)
        ]
    )
    assert len(calls) == 1, "il provider deve essere chiamato una volta sola per uno state"
    locations = [r.headers["location"] for r in responses]
    assert sum("connected=" in loc for loc in locations) == 1
    assert sum("error=invalid_state" in loc for loc in locations) == 2
    assert all(r.status_code == 307 for r in responses)
    assert len(await _connections(client, token)) == 1


# ---- M2: IP e user agent inoltrati alla banca ---------------------------------------


async def test_sync_ignores_client_supplied_forwarded_for_and_cleans_user_agent(client, httpx_mock, monkeypatch):
    token, _, _ = await _register(client, "sec-xff@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _, _ = await _enable_first_account(client, token)
    enqueue = AsyncMock(return_value="job")
    monkeypatch.setattr("app.api.v1.open_banking.enqueue_bank_sync", enqueue)
    response = await client.post(
        f"/api/v1/open-banking/connections/{connection_id}/sync",
        headers={**_h(token), "X-Forwarded-For": "6.6.6.6, 10.0.0.1", "User-Agent": "Mozilla\t" + "x" * 5000},
    )
    assert response.status_code == 202
    assert enqueue.call_args.kwargs["psu_ip"] != "6.6.6.6"
    ua = enqueue.call_args.kwargs["psu_user_agent"]
    assert len(ua) <= 256 and "\t" not in ua


def test_client_info_helpers_validate():
    class _Client:
        host = "not-an-ip"

    class _Request:
        client = _Client()

    assert client_ip(_Request()) is None
    _Client.host = "203.0.113.9"
    assert client_ip(_Request()) == "203.0.113.9"
    assert clean_user_agent("a\r\nInjected: 1") == "aInjected: 1"
    assert clean_user_agent("\x00\x01") is None
    assert len(clean_user_agent("y" * 999)) == 256


# ---- M5: scollegamento durante una sync -------------------------------------------


async def test_disconnect_is_refused_while_a_sync_holds_the_lock(client, httpx_mock):
    token, _, _ = await _register(client, "sec-disc@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _, _ = await _enable_first_account(client, token)
    assert await bank_sync_service.try_acquire_lock(uuid.UUID(connection_id))
    refused = await client.delete(
        f"/api/v1/open-banking/connections/{connection_id}?delete_data=true", headers=_h(token)
    )
    assert refused.status_code == 409
    assert len(await _connections(client, token)) == 1  # nulla e' stato cancellato

    await bank_sync_service.release_lock(uuid.UUID(connection_id))
    httpx_mock.add_response(url=f"{BASE}/sessions/sess-1", method="DELETE", status_code=204)
    ok = await client.delete(f"/api/v1/open-banking/connections/{connection_id}?delete_data=true", headers=_h(token))
    assert ok.status_code == 200
    assert not await bank_sync_service.is_sync_running(uuid.UUID(connection_id)), "il lock va rilasciato"


# ---- B3: limiti ------------------------------------------------------------------


async def test_manual_sync_has_a_cooldown(client, httpx_mock, monkeypatch):
    token, _, _ = await _register(client, "sec-cool@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _, _ = await _enable_first_account(client, token)
    monkeypatch.setattr("app.api.v1.open_banking.enqueue_bank_sync", AsyncMock(return_value="job"))
    url = f"/api/v1/open-banking/connections/{connection_id}/sync"
    assert (await client.post(url, headers=_h(token))).status_code == 202
    assert (await client.post(url, headers=_h(token))).status_code == 429


async def test_institutions_endpoint_is_rate_limited(client, httpx_mock):
    token, _, _ = await _register(client, "sec-inst@example.com")
    await _setup_credentials(client, token)
    codes = []
    for index in range(31):
        if index < 30:  # la 31esima viene respinta prima di raggiungere il provider
            httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", json={"aspsps": []})
        codes.append((await client.get("/api/v1/open-banking/institutions?country=IT", headers=_h(token))).status_code)
    assert codes[:30] == [200] * 30
    assert codes[30] == 429


# ---- B5: utente disattivato ----------------------------------------------------------


async def test_sync_skips_a_deactivated_user(client, httpx_mock):
    token, user_id, _ = await _register(client, "sec-inactive@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock)
    connection_id, _, _ = await _enable_first_account(client, token)
    async with rls_session(user_id) as db:
        await db.execute(text("UPDATE users SET is_active = false WHERE id = :i"), {"i": user_id})
        await db.commit()
    summary = await bank_sync_service.sync_connection(uuid.UUID(connection_id), user_id)
    assert summary.skipped is True and summary.accounts_synced == 0


# ---- B1: log -------------------------------------------------------------------------


def test_access_log_redacts_code_and_state():
    line = "/api/v1/open-banking/callback?code=SECRETCODE&state=eyJhbGciOi.payload.sig&x=1"
    redacted = redact_query_secrets(line)
    assert "SECRETCODE" not in redacted and "eyJhbGciOi" not in redacted
    assert "x=1" in redacted and redacted.startswith("/api/v1/open-banking/callback")


def test_uvicorn_access_filter_masks_request_line():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4", "GET", "/cb?code=ABC123&state=ST4TE", "1.1", 307),
        None,
    )
    assert RedactAccessLogFilter().filter(record) is True
    assert "ABC123" not in record.getMessage() and "ST4TE" not in record.getMessage()

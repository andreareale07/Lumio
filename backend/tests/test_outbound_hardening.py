"""Chiamate verso servizi esterni: proxy dei loghi, policy di uscita (SSRF),
dati anomali del provider. Dati sintetici, nessun traffico reale.
Richiede `OPEN_BANKING_ENABLED=true` (come test_open_banking_api.py)."""
import base64
import json
from decimal import Decimal

import httpx
import pytest

from app.core.config import get_settings
from app.core.outbound import OutboundBlocked, check_url_syntax, ensure_outbound_allowed, guarded_client
from app.core.redis import redis_client
from app.openbanking import logos as ob_logos
from app.openbanking.enable_banking import (
    EnableBankingConnector,
    _parse_amount,
    _parse_date,
    normalize_transaction,
)
from app.openbanking.errors import OpenBankingError
from tests.test_open_banking_api import BASE, _h, _register, _setup_credentials

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
async def _clean_logo_keys():
    async def wipe():
        async for key in redis_client.scan_iter(match="ob:logo:*"):
            await redis_client.delete(key)
        async for key in redis_client.scan_iter(match="LIMITER*"):
            await redis_client.delete(key)

    await wipe()
    yield
    await wipe()


# ---- policy di uscita -----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["http://169.254.169.254/latest/meta-data", "http://[fd00:ec2::254]/", "http://0.0.0.0/", "ftp://x.example/", "http://u:p@x.example/"],
)
def test_forbidden_outbound_urls(url):
    with pytest.raises(ValueError):
        check_url_syntax(url)


async def test_cloud_metadata_and_private_targets_are_blocked_at_request_time():
    with pytest.raises(OutboundBlocked):
        await ensure_outbound_allowed("http://169.254.169.254/latest/meta-data")
    # Un endpoint AI nella LAN resta ammesso (Ollama), ma non per i dati del provider.
    await ensure_outbound_allowed("http://192.168.1.20:11434")
    await ensure_outbound_allowed("http://localhost:11434")
    with pytest.raises(OutboundBlocked):
        await ensure_outbound_allowed("https://192.168.1.20/logo.png", public_only=True)
    with pytest.raises(OutboundBlocked):
        await ensure_outbound_allowed("https://127.0.0.1/logo.png", public_only=True)


async def test_guarded_client_refuses_before_sending(httpx_mock):
    async with guarded_client() as client:
        with pytest.raises(httpx.HTTPError):  # OutboundBlocked e' un errore di trasporto
            await client.get("http://169.254.169.254/latest/meta-data")
    assert httpx_mock.get_requests() == []


# ---- proxy dei loghi -------------------------------------------------------------


async def _register_logo(monkeypatch, url="https://cdn.example/b.png", payload=_PNG):
    async def fake_download(_url: str):
        return payload

    monkeypatch.setattr(ob_logos, "_download", fake_download)
    return (await ob_logos.register_logos([url]))[url]


async def test_logo_proxy_serves_cached_image_from_our_origin(client, monkeypatch):
    path = await _register_logo(monkeypatch)
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == _PNG


async def test_logo_proxy_rejects_unknown_keys_and_non_hex(client):
    assert (await client.get("/api/v1/open-banking/logos/" + "0" * 32)).status_code == 404
    assert (await client.get("/api/v1/open-banking/logos/..%2F..%2Fetc")).status_code == 404
    assert (await client.get("/api/v1/open-banking/logos/" + "g" * 32)).status_code == 404


async def test_logo_proxy_refuses_svg_and_non_images(client, monkeypatch):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    path = await _register_logo(monkeypatch, url="https://cdn.example/evil.svg", payload=svg)
    assert (await client.get(path)).status_code == 404
    html = b"<html><script>alert(1)</script></html>"
    path = await _register_logo(monkeypatch, url="https://cdn.example/x.png", payload=html)
    assert (await client.get(path)).status_code == 404


async def test_logo_download_enforces_size_limit_and_blocks_private_hosts(httpx_mock):
    httpx_mock.add_response(url="https://cdn.example/big.png", content=_PNG + b"0" * (ob_logos.MAX_LOGO_BYTES + 1))
    assert await ob_logos._download("https://cdn.example/big.png") is None
    # Host privato: rifiutato prima di inviare qualunque richiesta.
    assert await ob_logos._download("https://10.0.0.5/logo.png") is None
    assert [r.url.host for r in httpx_mock.get_requests()] == ["cdn.example"]


async def test_logo_download_does_not_follow_redirects(httpx_mock):
    httpx_mock.add_response(
        url="https://cdn.example/r.png", status_code=302, headers={"Location": "http://169.254.169.254/x"}
    )
    assert await ob_logos._download("https://cdn.example/r.png") is None
    assert len(httpx_mock.get_requests()) == 1


# ---- dati anomali dal provider -----------------------------------------------------


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e30", "abc", None])
def test_non_finite_or_absurd_amounts_are_rejected(value):
    assert _parse_amount(value) is None


def test_normal_amounts_and_dates_are_kept():
    assert _parse_amount("-12.50") == Decimal("-12.50")
    assert _parse_date("2026-11-06") is not None
    assert _parse_date("0001-01-01") is None and _parse_date("9999-12-31") is None


def test_transaction_with_nan_amount_is_skipped_and_huge_text_is_capped():
    assert normalize_transaction({"transaction_amount": {"amount": "NaN", "currency": "EUR"}, "booking_date": "2026-11-06"}) is None
    tx = normalize_transaction(
        {
            "transaction_amount": {"amount": "5.00", "currency": "EUR"},
            "credit_debit_indicator": "CRDT",
            "booking_date": "2026-11-06",
            "remittance_information": ["x" * 100_000],
            "debtor": {"name": "n" * 5000},
            "entry_reference": "e" * 5000,
        }
    )
    assert tx is not None
    assert len(tx.description) <= 2000 and len(tx.counterparty_name) <= 300 and len(tx.external_id) <= 200


async def test_oversized_provider_response_is_refused(httpx_mock):
    connector = EnableBankingConnector(application_id="app-id-synthetic-0001", private_key_pem=_test_key())
    httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", content=b"0" * (21 * 1024 * 1024))
    with pytest.raises(OpenBankingError) as caught:
        await connector.list_institutions("IT")
    assert caught.value.code == "response_too_large"


def _test_key() -> str:
    from app.openbanking.keys import generate_keypair

    return generate_keypair()[0]


# ---- configurazione di produzione ---------------------------------------------------


def test_production_pins_open_banking_host():
    import secrets

    from app.core.config import Settings

    base = {"database_url": "postgresql+asyncpg://x", "redis_url": "redis://x", "secret_key": secrets.token_urlsafe(64)}
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", open_banking_base_url="https://evil.example", **base)
    Settings(_env_file=None, app_env="production", open_banking_base_url="https://evil.example",
             open_banking_allow_custom_base_url=True, **base)
    Settings(_env_file=None, app_env="production", **base)


async def test_institutions_listing_has_no_provider_hostnames(client, httpx_mock):
    token, _, _ = await _register(client, "out-inst@example.com")
    await _setup_credentials(client, token)
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={"aspsps": [{"name": "B", "country": "IT", "logo": "https://cdn.example/b.png"}]},
    )
    response = await client.get("/api/v1/open-banking/institutions?country=IT", headers=_h(token))
    assert "cdn.example" not in response.text
    assert json.loads(response.text)[0]["logo_url"].startswith("/api/v1/open-banking/logos/")
    assert get_settings().open_banking_base_url

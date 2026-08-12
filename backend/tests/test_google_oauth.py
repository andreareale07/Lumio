"""Test unitari del client OAuth Google (milestone 10) — httpx mockato,
nessuna chiamata di rete reale (stesso principio di test_ai_providers.py).
"""
import time
import uuid

import pytest

from app.integrations.google.errors import GoogleAPIError, GoogleReauthRequiredError
from app.integrations.google.oauth import (
    GoogleCredentials,
    build_authorize_url,
    build_state,
    decode_state,
    exchange_code,
    fetch_account_email,
    get_valid_credentials,
    refresh_access_token,
    revoke,
)


def _credentials(**overrides) -> GoogleCredentials:
    defaults = dict(access_token="at", refresh_token="rt", expires_at=time.time() + 3600, scope="drive.file")
    defaults.update(overrides)
    return GoogleCredentials(**defaults)


def test_build_authorize_url_forces_offline_and_consent_for_refresh_token():
    url = build_authorize_url("some-state")
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=some-state" in url
    assert "drive.file" in url


def test_credentials_json_roundtrip():
    creds = _credentials()
    assert GoogleCredentials.from_json(creds.to_json()) == creds


def test_credentials_is_expired_within_safety_margin():
    assert _credentials(expires_at=time.time() + 30).is_expired is True


def test_credentials_not_expired_when_far_in_future():
    assert _credentials(expires_at=time.time() + 3600).is_expired is False


async def test_exchange_code_returns_credentials(httpx_mock):
    httpx_mock.add_response(
        url="https://oauth2.googleapis.com/token",
        json={"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 3600, "scope": "drive.file"},
    )
    creds = await exchange_code("auth-code")
    assert creds.access_token == "new-at"
    assert creds.refresh_token == "new-rt"


async def test_exchange_code_without_refresh_token_raises(httpx_mock):
    httpx_mock.add_response(
        url="https://oauth2.googleapis.com/token", json={"access_token": "new-at", "expires_in": 3600}
    )
    with pytest.raises(GoogleAPIError, match="refresh_token"):
        await exchange_code("auth-code")


async def test_refresh_access_token_reuses_existing_refresh_token(httpx_mock):
    httpx_mock.add_response(url="https://oauth2.googleapis.com/token", json={"access_token": "refreshed-at", "expires_in": 3600})
    refreshed = await refresh_access_token(_credentials(refresh_token="stable-rt"))
    assert refreshed.access_token == "refreshed-at"
    assert refreshed.refresh_token == "stable-rt"


async def test_refresh_access_token_invalid_grant_raises_reauth_required(httpx_mock):
    httpx_mock.add_response(url="https://oauth2.googleapis.com/token", status_code=400, json={"error": "invalid_grant"})
    with pytest.raises(GoogleReauthRequiredError):
        await refresh_access_token(_credentials())


async def test_get_valid_credentials_skips_refresh_when_not_expired():
    creds = _credentials(expires_at=time.time() + 3600)
    # Nessun httpx_mock registrato: se questa funzione facesse comunque una
    # chiamata di rete, il test fallirebbe con un errore di connessione.
    assert await get_valid_credentials(creds) is creds


async def test_revoke_treats_already_invalid_token_as_success(httpx_mock):
    httpx_mock.add_response(url="https://oauth2.googleapis.com/revoke", json={})
    await revoke(_credentials())  # non deve sollevare


async def test_revoke_raises_on_server_error(httpx_mock):
    httpx_mock.add_response(url="https://oauth2.googleapis.com/revoke", status_code=500)
    with pytest.raises(GoogleAPIError):
        await revoke(_credentials())


async def test_fetch_account_email(httpx_mock):
    httpx_mock.add_response(url="https://openidconnect.googleapis.com/v1/userinfo", json={"email": "user@example.com"})
    assert await fetch_account_email(_credentials()) == "user@example.com"


def test_state_roundtrip():
    workspace_id, user_id = uuid.uuid4(), uuid.uuid4()
    assert decode_state(build_state(workspace_id, user_id)) == (workspace_id, user_id)


def test_decode_state_rejects_garbage():
    assert decode_state("not-a-valid-jwt") is None

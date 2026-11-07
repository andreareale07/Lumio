import pyotp
from httpx import AsyncClient

PASSWORD = "correct-password-123"


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": "T"}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _enable_totp(client: AsyncClient, headers: dict) -> str:
    setup = await client.post("/api/v1/auth/totp/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    response = await client.post(
        "/api/v1/auth/totp/enable", headers=headers, json={"code": pyotp.TOTP(secret).now()}
    )
    assert response.status_code == 204
    return secret


async def _login(client: AsyncClient, email: str, code: str | None = None):
    body = {"email": email, "password": PASSWORD}
    if code is not None:
        body["totp_code"] = code
    return await client.post("/api/v1/auth/login", json=body)


async def test_login_without_2fa_unchanged(client):
    await _register(client, "plain@example.com")
    response = await _login(client, "plain@example.com")
    assert response.status_code == 200
    assert response.json()["user"]["totp_enabled"] is False


async def test_setup_does_not_enable_until_code_verified(client):
    headers = await _register(client, "pending@example.com")
    setup = await client.post("/api/v1/auth/totp/setup", headers=headers)
    assert setup.status_code == 200
    # Segreto in attesa: il login non chiede ancora il codice.
    assert (await _login(client, "pending@example.com")).status_code == 200
    wrong = await client.post("/api/v1/auth/totp/enable", headers=headers, json={"code": "000000"})
    assert wrong.status_code == 400


async def test_login_requires_code_when_enabled(client):
    headers = await _register(client, "two@example.com")
    secret = await _enable_totp(client, headers)

    missing = await _login(client, "two@example.com")
    assert missing.status_code == 401
    assert missing.json()["detail"] == "TOTP_REQUIRED"

    invalid = await _login(client, "two@example.com", "123456" if pyotp.TOTP(secret).now() != "123456" else "654321")
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "TOTP_INVALID"


async def test_login_with_valid_code_and_replay_rejected(client):
    headers = await _register(client, "ok@example.com")
    secret = await _enable_totp(client, headers)
    totp = pyotp.TOTP(secret)
    # Il codice usato per l'attivazione e' gia' "bruciato": serve quello della finestra successiva.
    code = totp.at(__import__("time").time() + 30)
    first = await _login(client, "ok@example.com", code)
    assert first.status_code == 200
    assert first.json()["user"]["totp_enabled"] is True
    replay = await _login(client, "ok@example.com", code)
    assert replay.status_code == 401
    assert replay.json()["detail"] == "TOTP_INVALID"


async def test_wrong_password_never_reveals_totp_state(client):
    headers = await _register(client, "hide@example.com")
    await _enable_totp(client, headers)
    response = await client.post(
        "/api/v1/auth/login", json={"email": "hide@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_disable_requires_password_and_code(client):
    headers = await _register(client, "off@example.com")
    secret = await _enable_totp(client, headers)
    code = pyotp.TOTP(secret).at(__import__("time").time() + 30)

    bad_password = await client.post(
        "/api/v1/auth/totp/disable", headers=headers, json={"password": "nope-nope-123", "code": code}
    )
    assert bad_password.status_code == 400

    ok = await client.post(
        "/api/v1/auth/totp/disable", headers=headers, json={"password": PASSWORD, "code": code}
    )
    assert ok.status_code == 204
    assert (await _login(client, "off@example.com")).status_code == 200


async def test_secret_is_encrypted_and_not_exposed_by_me(client):
    headers = await _register(client, "me@example.com")
    await _enable_totp(client, headers)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["totp_enabled"] is True
    assert "secret" not in str(me.json()).lower()


async def test_native_client_gets_refresh_token_in_body(client):
    await _register(client, "native@example.com")
    web = await _login(client, "native@example.com")
    assert web.json()["refresh_token"] is None

    native = await client.post(
        "/api/v1/auth/login",
        json={"email": "native@example.com", "password": PASSWORD},
        headers={"X-Lumio-Client": "native"},
    )
    token = native.json()["refresh_token"]
    assert token
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": token}, headers={"X-Lumio-Client": "native"}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] not in (None, token)

"""App mobile: auth del guscio nativo (refresh token nel body), CORS dell'app,
registrazione dei dispositivi push e "conferma" da swipe."""
import uuid

from httpx import AsyncClient

NATIVE = {"X-Lumio-Client": "native"}
PASSWORD = "correct-password-123"


async def _register(client: AsyncClient, email: str, headers: dict | None = None):
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "T"},
        headers=headers or {},
    )


async def test_web_client_never_gets_refresh_token_in_body(client):
    response = await _register(client, "web@example.com")

    assert response.status_code == 201
    assert response.json()["refresh_token"] is None
    assert "refresh_token" in response.cookies


async def test_native_client_gets_refresh_token_in_body_and_no_cookie(client):
    response = await _register(client, "native@example.com", NATIVE)

    body = response.json()
    assert body["refresh_token"]
    assert "refresh_token" not in response.cookies


async def test_native_refresh_rotates_token_from_body(client):
    first = (await _register(client, "rot@example.com", NATIVE)).json()["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": first}, headers=NATIVE)
    assert refreshed.status_code == 200
    second = refreshed.json()["refresh_token"]
    assert second and second != first

    # Il vecchio token e' stato ruotato: non vale piu'.
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": first}, headers=NATIVE)
    assert replay.status_code == 401


async def test_native_refresh_without_token_is_401_with_detail(client):
    # Il test di connessione dell'app si basa su questa risposta (401 + JSON con `detail`).
    response = await client.post("/api/v1/auth/refresh", headers=NATIVE)

    assert response.status_code == 401
    assert isinstance(response.json()["detail"], str)


async def test_native_logout_revokes_token(client):
    token = (await _register(client, "out@example.com", NATIVE)).json()["refresh_token"]

    out = await client.post("/api/v1/auth/logout", json={"refresh_token": token}, headers=NATIVE)
    assert out.status_code == 204

    again = await client.post("/api/v1/auth/refresh", json={"refresh_token": token}, headers=NATIVE)
    assert again.status_code == 401


async def test_body_token_is_ignored_for_non_native_clients(client):
    token = (await _register(client, "ign@example.com", NATIVE)).json()["refresh_token"]
    client.cookies.clear()

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})

    assert response.status_code == 401


async def test_cors_allows_app_origin_without_credentials(client):
    response = await client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-lumio-client",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost"
    assert "access-control-allow-credentials" not in response.headers


async def test_cors_rejects_unknown_origin(client):
    response = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in response.headers


async def _auth_headers(client: AsyncClient, email: str) -> dict:
    body = (await _register(client, email)).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


async def test_push_device_registration_is_idempotent_and_removable(client):
    headers = await _auth_headers(client, "push@example.com")
    token = "fcm-token-" + uuid.uuid4().hex

    for _ in range(2):
        created = await client.post("/api/v1/push/devices", json={"token": token, "platform": "android"}, headers=headers)
        assert created.status_code == 204

    status_response = await client.get("/api/v1/push/status", headers=headers)
    assert status_response.json() == {"configured": False, "devices": 1}

    removed = await client.request("DELETE", "/api/v1/push/devices", json={"token": token}, headers=headers)
    assert removed.status_code == 204
    assert (await client.get("/api/v1/push/status", headers=headers)).json()["devices"] == 0


async def test_push_devices_are_private_to_each_user(client):
    alice = await _auth_headers(client, "alice-push@example.com")
    bob = await _auth_headers(client, "bob-push@example.com")
    token = "fcm-token-" + uuid.uuid4().hex
    await client.post("/api/v1/push/devices", json={"token": token, "platform": "android"}, headers=alice)

    assert (await client.get("/api/v1/push/status", headers=bob)).json()["devices"] == 0
    # Bob non puo' cancellare il dispositivo di Alice.
    await client.request("DELETE", "/api/v1/push/devices", json={"token": token}, headers=bob)
    assert (await client.get("/api/v1/push/status", headers=alice)).json()["devices"] == 1


async def test_push_requires_auth(client):
    response = await client.post("/api/v1/push/devices", json={"token": "x" * 20, "platform": "android"})

    assert response.status_code == 401


async def test_patch_needs_review_only_accepts_false(client):
    headers = await _auth_headers(client, "review@example.com")

    response = await client.patch(f"/api/v1/transactions/{uuid.uuid4()}", json={"needs_review": True}, headers=headers)

    assert response.status_code == 422

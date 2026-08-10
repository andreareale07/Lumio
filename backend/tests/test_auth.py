from httpx import AsyncClient


async def _register(
    client: AsyncClient,
    email: str,
    password: str = "correct-password-123",
    display_name: str = "Test",
):
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )


async def test_register_creates_user_and_personal_workspace(client):
    response = await _register(client, "alice@example.com")

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["workspace_id"]
    assert body["access_token"]


async def test_register_duplicate_email_rejected(client):
    await _register(client, "dup@example.com")
    response = await _register(client, "dup@example.com")

    assert response.status_code == 409


async def test_login_with_correct_password(client):
    await _register(client, "bob@example.com")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "correct-password-123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_with_wrong_password_rejected(client):
    await _register(client, "carl@example.com")
    response = await client.post(
        "/api/v1/auth/login", json={"email": "carl@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


async def test_login_unknown_email_rejected(client):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )

    assert response.status_code == 401


async def test_me_requires_valid_token(client):
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_with_garbage_token_rejected(client):
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


async def test_me_returns_current_user(client):
    register_response = await _register(client, "dana@example.com")
    token = register_response.json()["access_token"]

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "dana@example.com"


async def test_refresh_issues_new_token_and_rotates_old_one(client):
    await _register(client, "erin@example.com")
    old_cookie = client.cookies.get("refresh_token")
    assert old_cookie is not None

    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]

    client.cookies.set("refresh_token", old_cookie)
    reuse_response = await client.post("/api/v1/auth/refresh")
    assert reuse_response.status_code == 401


async def test_refresh_without_cookie_rejected(client):
    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401


async def test_logout_revokes_refresh_token(client):
    await _register(client, "frank@example.com")

    logout_response = await client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204

    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


async def test_user_a_cannot_see_user_b_workspace_via_api(client):
    resp_a = await _register(client, "usera@example.com")
    resp_b = await _register(client, "userb@example.com")

    workspace_a = resp_a.json()["user"]["workspace_id"]
    workspace_b = resp_b.json()["user"]["workspace_id"]
    assert workspace_a != workspace_b

    token_a = resp_a.json()["access_token"]
    me_a = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})

    assert me_a.json()["workspace_id"] == workspace_a

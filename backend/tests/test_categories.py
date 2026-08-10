from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_list_categories_includes_system_categories(client):
    token = await _register(client, "cat-viewer@example.com")

    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    assert response.status_code == 200
    codes = {c["code"] for c in response.json()}
    assert "casa" in codes
    assert "alimentari.supermercato" in codes


async def test_create_update_delete_custom_category(client):
    token = await _register(client, "cat-owner@example.com")

    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Hobby", "code": "hobby"},
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    category = create_response.json()
    assert category["is_system"] is False

    update_response = await client.patch(
        f"/api/v1/categories/{category['id']}",
        json={"name": "Hobby personali"},
        headers=_auth_headers(token),
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Hobby personali"

    delete_response = await client.delete(
        f"/api/v1/categories/{category['id']}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204


async def test_cannot_modify_system_category(client):
    token = await _register(client, "cat-hacker@example.com")

    list_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    system_category = next(c for c in list_response.json() if c["is_system"])

    update_response = await client.patch(
        f"/api/v1/categories/{system_category['id']}",
        json={"name": "Hacked"},
        headers=_auth_headers(token),
    )
    assert update_response.status_code == 403

    delete_response = await client.delete(
        f"/api/v1/categories/{system_category['id']}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 403


async def test_user_a_cannot_modify_user_b_custom_category_via_api(client):
    token_a = await _register(client, "cat-a@example.com")
    token_b = await _register(client, "cat-b@example.com")

    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Privata di B", "code": "privata-b"},
        headers=_auth_headers(token_b),
    )
    category_b_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/api/v1/categories/{category_b_id}",
        json={"name": "Hacked"},
        headers=_auth_headers(token_a),
    )
    assert update_response.status_code == 404

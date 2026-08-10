from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _system_category_id(client: AsyncClient, token: str, code: str = "abbonamenti.streaming") -> str:
    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    return next(c["id"] for c in response.json() if c["code"] == code)


def _rule_payload(category_id: str, **overrides) -> dict:
    payload = {
        "name": "Netflix",
        "field": "description",
        "operator": "contains",
        "value": "netflix",
        "category_id": category_id,
    }
    payload.update(overrides)
    return payload


async def test_create_list_update_delete_rule(client):
    token = await _register(client, "rule-owner@example.com")
    category_id = await _system_category_id(client, token)

    create_response = await client.post(
        "/api/v1/rules", json=_rule_payload(category_id), headers=_auth_headers(token)
    )
    assert create_response.status_code == 201
    rule = create_response.json()
    assert rule["is_active"] is True
    assert rule["priority"] == 100

    list_response = await client.get("/api/v1/rules", headers=_auth_headers(token))
    assert [r["id"] for r in list_response.json()] == [rule["id"]]

    update_response = await client.patch(
        f"/api/v1/rules/{rule['id']}", json={"is_active": False}, headers=_auth_headers(token)
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_active"] is False

    delete_response = await client.delete(f"/api/v1/rules/{rule['id']}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    list_after_delete = await client.get("/api/v1/rules", headers=_auth_headers(token))
    assert list_after_delete.json() == []


async def test_create_rule_rejects_invalid_regex(client):
    token = await _register(client, "rule-regex@example.com")
    category_id = await _system_category_id(client, token)

    response = await client.post(
        "/api/v1/rules",
        json=_rule_payload(category_id, operator="regex", value="[unterminated"),
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_merchant_equals_requires_merchant_field(client):
    token = await _register(client, "rule-merchant@example.com")
    category_id = await _system_category_id(client, token)

    response = await client.post(
        "/api/v1/rules",
        json=_rule_payload(category_id, field="description", operator="merchant_equals"),
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_create_rule_rejects_category_from_another_workspace(client):
    token_a = await _register(client, "rule-cross-a@example.com")
    token_b = await _register(client, "rule-cross-b@example.com")

    custom_category = await client.post(
        "/api/v1/categories",
        json={"name": "Privata di B", "code": "privata-b"},
        headers=_auth_headers(token_b),
    )
    category_b_id = custom_category.json()["id"]

    response = await client.post(
        "/api/v1/rules", json=_rule_payload(category_b_id), headers=_auth_headers(token_a)
    )
    assert response.status_code == 400


async def test_user_a_cannot_see_or_modify_user_b_rule_via_api(client):
    token_a = await _register(client, "rule-iso-a@example.com")
    token_b = await _register(client, "rule-iso-b@example.com")
    category_b_id = await _system_category_id(client, token_b)

    create_response = await client.post(
        "/api/v1/rules", json=_rule_payload(category_b_id), headers=_auth_headers(token_b)
    )
    rule_b_id = create_response.json()["id"]

    get_response = await client.get(f"/api/v1/rules/{rule_b_id}", headers=_auth_headers(token_a))
    assert get_response.status_code == 404

    update_response = await client.patch(
        f"/api/v1/rules/{rule_b_id}", json={"is_active": False}, headers=_auth_headers(token_a)
    )
    assert update_response.status_code == 404

    list_response = await client.get("/api/v1/rules", headers=_auth_headers(token_a))
    assert list_response.json() == []

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


async def test_cannot_delete_category_in_use_by_a_transaction(client):
    token = await _register(client, "cat-in-use@example.com")

    account = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    category = await client.post(
        "/api/v1/categories",
        json={"name": "Hobby", "code": "hobby"},
        headers=_auth_headers(token),
    )
    category_id = category.json()["id"]

    transaction = await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id,
            "transaction_date": "2026-01-01",
            "amount": "-10.00",
            "currency": "EUR",
            "direction": "debit",
            "description_raw": "Test",
            "transaction_type": "expense",
            "category_id": category_id,
        },
        headers=_auth_headers(token),
    )
    assert transaction.status_code == 201, transaction.text

    delete_response = await client.delete(
        f"/api/v1/categories/{category_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 409

    # La categoria non deve essere stata cancellata nonostante il rollback avvenga dopo il flush del delete.
    list_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    assert category_id in {c["id"] for c in list_response.json()}


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

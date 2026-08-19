from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_create_and_list_account(client):
    token = await _register(client, "acc-owner@example.com")

    create_response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto Corrente", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    account = create_response.json()
    assert account["name"] == "Conto Corrente"
    assert account["is_active"] is True

    list_response = await client.get("/api/v1/accounts", headers=_auth_headers(token))
    assert list_response.status_code == 200
    assert [a["id"] for a in list_response.json()] == [account["id"]]


async def test_update_and_delete_account(client):
    token = await _register(client, "acc-editor@example.com")
    create_response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"name": "Conto Rinominato", "is_active": False},
        headers=_auth_headers(token),
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Conto Rinominato"
    assert update_response.json()["is_active"] is False

    delete_response = await client.delete(
        f"/api/v1/accounts/{account_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/accounts/{account_id}", headers=_auth_headers(token)
    )
    assert get_response.status_code == 404


async def test_create_account_rejects_unknown_currency_code(client):
    token = await _register(client, "acc-invalid-currency@example.com")
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "XXX"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


async def test_update_account_rejects_unknown_currency_code(client):
    token = await _register(client, "acc-invalid-currency-update@example.com")
    create_response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = create_response.json()["id"]

    response = await client.patch(
        f"/api/v1/accounts/{account_id}", json={"currency": "XXX"}, headers=_auth_headers(token)
    )
    assert response.status_code == 400


async def test_user_a_cannot_see_user_b_account_via_api(client):
    token_a = await _register(client, "acc-a@example.com")
    token_b = await _register(client, "acc-b@example.com")

    create_response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto di B", "account_type": "savings", "currency": "EUR"},
        headers=_auth_headers(token_b),
    )
    account_b_id = create_response.json()["id"]

    get_response = await client.get(
        f"/api/v1/accounts/{account_b_id}", headers=_auth_headers(token_a)
    )
    assert get_response.status_code == 404

    list_response = await client.get("/api/v1/accounts", headers=_auth_headers(token_a))
    assert list_response.json() == []

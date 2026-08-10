from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


def _transaction_payload(account_id: str, **overrides) -> dict:
    payload = {
        "financial_account_id": account_id,
        "transaction_date": "2026-08-01",
        "description_raw": "SUPERMERCATO LIDL MILANO",
        "amount": "-42.50",
        "currency": "EUR",
        "direction": "debit",
        "transaction_type": "expense",
    }
    payload.update(overrides)
    return payload


async def test_create_and_list_transaction(client):
    token = await _register(client, "tx-owner@example.com")
    account_id = await _create_account(client, token)

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    transaction = create_response.json()
    assert transaction["description_raw"] == "SUPERMERCATO LIDL MILANO"
    assert transaction["amount"] == "-42.50"

    list_response = await client.get("/api/v1/transactions", headers=_auth_headers(token))
    assert list_response.status_code == 200
    assert [t["id"] for t in list_response.json()] == [transaction["id"]]


async def test_create_transaction_rejects_foreign_account(client):
    token_a = await _register(client, "tx-cross-a@example.com")
    token_b = await _register(client, "tx-cross-b@example.com")
    account_b_id = await _create_account(client, token_b)

    response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_b_id),
        headers=_auth_headers(token_a),
    )
    assert response.status_code == 400


async def test_update_transaction_category(client):
    token = await _register(client, "tx-editor@example.com")
    account_id = await _create_account(client, token)
    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    categories_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    supermarket_category = next(
        c for c in categories_response.json() if c["code"] == "alimentari.supermercato"
    )

    update_response = await client.patch(
        f"/api/v1/transactions/{transaction_id}",
        json={"category_id": supermarket_category["id"]},
        headers=_auth_headers(token),
    )
    assert update_response.status_code == 200
    assert update_response.json()["category_id"] == supermarket_category["id"]


async def test_user_a_cannot_see_user_b_transaction_via_api(client):
    token_a = await _register(client, "tx-a@example.com")
    token_b = await _register(client, "tx-b@example.com")
    account_b_id = await _create_account(client, token_b)

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_b_id),
        headers=_auth_headers(token_b),
    )
    transaction_b_id = create_response.json()["id"]

    get_response = await client.get(
        f"/api/v1/transactions/{transaction_b_id}", headers=_auth_headers(token_a)
    )
    assert get_response.status_code == 404

    list_response = await client.get("/api/v1/transactions", headers=_auth_headers(token_a))
    assert list_response.json() == []


async def test_delete_transaction(client):
    token = await _register(client, "tx-deleter@example.com")
    account_id = await _create_account(client, token)
    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token)
    )
    assert get_response.status_code == 404

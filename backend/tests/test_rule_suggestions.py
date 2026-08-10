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


async def _category_id(client: AsyncClient, token: str, code: str) -> str:
    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    return next(c["id"] for c in response.json() if c["code"] == code)


async def _create_transaction(client: AsyncClient, token: str, account_id: str, description: str) -> str:
    response = await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id,
            "transaction_date": "2026-08-01",
            "description_raw": description,
            "amount": "-9.99",
            "currency": "EUR",
            "direction": "debit",
            "transaction_type": "expense",
        },
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def test_single_correction_does_not_trigger_suggestion(client):
    token = await _register(client, "suggest-single@example.com")
    account_id = await _create_account(client, token)
    category_id = await _category_id(client, token, "abbonamenti.streaming")
    transaction_id = await _create_transaction(client, token, account_id, "Pagamento NETFLIX.COM")

    await client.patch(
        f"/api/v1/transactions/{transaction_id}",
        json={"category_id": category_id},
        headers=_auth_headers(token),
    )

    suggestions = await client.get("/api/v1/rules/suggestions", headers=_auth_headers(token))
    assert suggestions.json() == []


async def test_repeated_correction_on_same_description_triggers_suggestion(client):
    token = await _register(client, "suggest-repeat@example.com")
    account_id = await _create_account(client, token)
    category_id = await _category_id(client, token, "abbonamenti.streaming")

    tx1 = await _create_transaction(client, token, account_id, "Pagamento NETFLIX.COM")
    tx2 = await _create_transaction(client, token, account_id, "pagamento netflix.com")
    for transaction_id in (tx1, tx2):
        await client.patch(
            f"/api/v1/transactions/{transaction_id}",
            json={"category_id": category_id},
            headers=_auth_headers(token),
        )

    suggestions_response = await client.get("/api/v1/rules/suggestions", headers=_auth_headers(token))
    assert suggestions_response.status_code == 200
    suggestions = suggestions_response.json()
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion["match_field"] == "description"
    assert suggestion["category_id"] == category_id
    assert suggestion["occurrences"] == 2
    assert sorted(suggestion["transaction_ids"]) == sorted([tx1, tx2])


async def test_suggestion_disappears_once_a_covering_rule_exists(client):
    token = await _register(client, "suggest-covered@example.com")
    account_id = await _create_account(client, token)
    category_id = await _category_id(client, token, "abbonamenti.streaming")

    tx1 = await _create_transaction(client, token, account_id, "Pagamento NETFLIX.COM")
    tx2 = await _create_transaction(client, token, account_id, "Pagamento NETFLIX.COM")
    for transaction_id in (tx1, tx2):
        await client.patch(
            f"/api/v1/transactions/{transaction_id}",
            json={"category_id": category_id},
            headers=_auth_headers(token),
        )

    before = await client.get("/api/v1/rules/suggestions", headers=_auth_headers(token))
    assert len(before.json()) == 1

    await client.post(
        "/api/v1/rules",
        json={
            "name": "Netflix",
            "field": "description",
            "operator": "contains",
            "value": "netflix",
            "category_id": category_id,
        },
        headers=_auth_headers(token),
    )

    after = await client.get("/api/v1/rules/suggestions", headers=_auth_headers(token))
    assert after.json() == []

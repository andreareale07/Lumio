async def test_list_banks_requires_auth(client):
    response = await client.get("/api/v1/banks")
    assert response.status_code == 401


async def test_list_banks_returns_seeded_reference_data(client):
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bank-viewer@example.com",
            "password": "correct-password-123",
            "display_name": "Test",
        },
    )
    token = register_response.json()["access_token"]

    response = await client.get(
        "/api/v1/banks", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    codes = {b["code"] for b in response.json()}
    assert {"trade_republic", "bancoposta", "fineco", "revolut", "other"} <= codes

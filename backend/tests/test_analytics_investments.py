"""Verifica che `/analytics/balances` esponga il valore REALE delle
posizioni (milestone 09b) — prima di questa milestone `investment_total`
era sempre cablato a 0/False (vedi commento storico in `analytics.py`).
"""
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
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def _create_asset(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/v1/assets",
        json={"name": "Vanguard FTSE All-World", "symbol": "VWCE", "asset_type": "etf", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def test_balances_reflect_real_position_at_cost_without_market_data(client):
    token = await _register(client, "analytics-investments@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    await client.post(
        "/api/v1/investment-transactions",
        json={
            "financial_account_id": account_id,
            "asset_id": asset_id,
            "trade_date": "2026-01-15",
            "type": "buy",
            "quantity": "10",
            "price": "100.00",
            "amount": "-1000.00",
            "currency": "EUR",
        },
        headers=_auth_headers(token),
    )

    response = await client.get("/api/v1/analytics/balances", headers=_auth_headers(token))
    body = response.json()
    # Nessun MarketDataProvider configurato: valorizzazione a costo
    # storico, mai un crash (DoD M09).
    assert body["investment_total"] == "1000.00"
    assert body["has_investments"] is True


async def test_balances_use_market_price_when_available(client):
    token = await _register(client, "analytics-investments-price@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    await client.post(
        "/api/v1/investment-transactions",
        json={
            "financial_account_id": account_id,
            "asset_id": asset_id,
            "trade_date": "2026-01-15",
            "type": "buy",
            "quantity": "10",
            "price": "100.00",
            "amount": "-1000.00",
            "currency": "EUR",
        },
        headers=_auth_headers(token),
    )
    await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "120.00", "currency": "EUR"},
        headers=_auth_headers(token),
    )

    response = await client.get(
        "/api/v1/analytics/balances", params={"as_of": "2026-08-01"}, headers=_auth_headers(token)
    )
    body = response.json()
    assert body["investment_total"] == "1200.00"
    assert body["has_investments"] is True


async def test_balances_have_no_investments_when_no_positions(client):
    token = await _register(client, "analytics-investments-none@example.com")
    await _create_account(client, token)

    response = await client.get("/api/v1/analytics/balances", headers=_auth_headers(token))
    body = response.json()
    assert body["investment_total"] == "0.00"
    assert body["has_investments"] is False

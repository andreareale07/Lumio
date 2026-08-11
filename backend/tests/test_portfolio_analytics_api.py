"""Test degli endpoint di analytics del portfolio (milestone 09b):
valuation/allocation live, performance/net-worth-history letti dagli
snapshot — mai ricalcolati al volo (DoD M09).
"""
from httpx import AsyncClient

from app.worker.jobs.snapshot import write_snapshot_for_workspace


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/accounts", json=payload, headers=_auth_headers(token))
    return response.json()["id"]


async def _create_asset(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Vanguard FTSE All-World", "symbol": "VWCE", "asset_type": "etf", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/assets", json=payload, headers=_auth_headers(token))
    return response.json()["id"]


async def _buy(client: AsyncClient, token: str, account_id: str, asset_id: str, **overrides) -> None:
    payload = {
        "financial_account_id": account_id,
        "asset_id": asset_id,
        "trade_date": "2026-01-15",
        "type": "buy",
        "quantity": "10",
        "price": "100.00",
        "amount": "-1000.00",
        "currency": "EUR",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/investment-transactions", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text


async def test_valuation_endpoint_does_not_collide_with_portfolio_id_route(client):
    """Regressione: '/portfolios/analytics/valuation' non deve essere
    interpretato come '/portfolios/{portfolio_id}' con portfolio_id="analytics"."""
    token = await _register(client, "pf-analytics-route@example.com")
    response = await client.get("/api/v1/portfolios/analytics/valuation", headers=_auth_headers(token))
    assert response.status_code == 200, response.text


async def test_valuation_falls_back_to_cost_without_market_data(client):
    token = await _register(client, "pf-valuation-cost@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)

    response = await client.get("/api/v1/portfolios/analytics/valuation", headers=_auth_headers(token))
    body = response.json()
    assert body["market_value"] == "1000.00"
    assert body["cost_basis"] == "1000.00"
    assert body["has_market_data"] is False  # nessun prezzo per questo asset
    assert body["has_holdings"] is True


async def test_valuation_uses_market_price_when_available(client):
    token = await _register(client, "pf-valuation-price@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)
    await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "120.00", "currency": "EUR"},
        headers=_auth_headers(token),
    )

    response = await client.get(
        "/api/v1/portfolios/analytics/valuation",
        params={"as_of": "2026-08-01"},
        headers=_auth_headers(token),
    )
    body = response.json()
    assert body["market_value"] == "1200.00"
    assert body["unrealized_pl"] == "200.00"
    assert body["has_market_data"] is True


async def test_allocation_groups_by_asset_type_asset_and_account(client):
    token = await _register(client, "pf-allocation@example.com")
    account_id = await _create_account(client, token)
    etf_id = await _create_asset(client, token, name="ETF World", symbol="VWCE", asset_type="etf")
    stock_id = await _create_asset(client, token, name="Apple", symbol="AAPL", asset_type="stock")
    await _buy(client, token, account_id, etf_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_id, stock_id, quantity="5", price="200.00", amount="-1000.00")

    response = await client.get("/api/v1/portfolios/analytics/allocation", headers=_auth_headers(token))
    body = response.json()
    assert {item["key"] for item in body["by_asset_type"]} == {"etf", "stock"}
    total_share = sum(float(item["share"]) for item in body["by_asset_type"])
    assert abs(total_share - 1.0) < 0.01
    assert len(body["by_asset"]) == 2
    assert len(body["by_account"]) == 1


async def test_allocation_scoped_to_portfolio_excludes_other_accounts(client):
    token = await _register(client, "pf-allocation-scoped@example.com")
    account_in = await _create_account(client, token, name="Dentro il portfolio")
    account_out = await _create_account(client, token, name="Fuori dal portfolio")
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_in, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_out, asset_id, quantity="5", price="100.00", amount="-500.00")

    portfolio = await client.post(
        "/api/v1/portfolios", json={"name": "Solo un conto", "currency": "EUR"}, headers=_auth_headers(token)
    )
    portfolio_id = portfolio.json()["id"]
    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/accounts",
        json={"financial_account_id": account_in},
        headers=_auth_headers(token),
    )

    scoped = await client.get(
        "/api/v1/portfolios/analytics/valuation",
        params={"portfolio_id": portfolio_id},
        headers=_auth_headers(token),
    )
    aggregate = await client.get("/api/v1/portfolios/analytics/valuation", headers=_auth_headers(token))
    assert scoped.json()["cost_basis"] == "1000.00"
    assert aggregate.json()["cost_basis"] == "1500.00"


async def test_performance_and_net_worth_history_read_from_snapshots(client):
    token = await _register(client, "pf-performance@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = me.json()["workspace_id"]
    user_id = me.json()["id"]
    await write_snapshot_for_workspace(None, workspace_id, user_id)

    # Un secondo acquisto DOPO lo snapshot non deve alterare il punto
    # storico gia' scritto (DoD: "non ricalcolato da zero ogni volta").
    await _buy(
        client, token, account_id, asset_id, trade_date="2026-06-01", quantity="5", price="200.00", amount="-1000.00"
    )

    performance = await client.get("/api/v1/portfolios/analytics/performance", headers=_auth_headers(token))
    points = performance.json()["points"]
    assert len(points) == 1
    assert points[0]["cost_basis"] == "1000.00"  # non "2000.00"

    net_worth = await client.get("/api/v1/analytics/net-worth-history", headers=_auth_headers(token))
    nw_points = net_worth.json()["points"]
    assert len(nw_points) == 1
    assert nw_points[0]["investments"] == "1000.00"

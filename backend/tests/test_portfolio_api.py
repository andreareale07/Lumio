"""Test API del dominio Portfolio (milestone 09a) — CRUD + logica di
business end-to-end (senza market data, tutto a costo storico: M09b).
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


async def _create_account(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/accounts", json=payload, headers=_auth_headers(token))
    return response.json()["id"]


async def _create_asset(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Vanguard FTSE All-World", "symbol": "VWCE", "asset_type": "etf", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/assets", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_investment_transaction(
    client: AsyncClient, token: str, account_id: str, **overrides
) -> dict:
    payload = {
        "financial_account_id": account_id,
        "trade_date": "2026-01-15",
        "type": "buy",
        "quantity": "10",
        "price": "100.00",
        "amount": "-1000.00",
        "currency": "EUR",
    }
    payload.update(overrides)
    response = await client.post(
        "/api/v1/investment-transactions", json=payload, headers=_auth_headers(token)
    )
    return response


# --- Assets ------------------------------------------------------------------


async def test_asset_crud(client):
    token = await _register(client, "asset-crud@example.com")
    asset_id = await _create_asset(client, token)

    get_resp = await client.get(f"/api/v1/assets/{asset_id}", headers=_auth_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["symbol"] == "VWCE"

    update_resp = await client.patch(
        f"/api/v1/assets/{asset_id}", json={"notes": "PAC mensile"}, headers=_auth_headers(token)
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["notes"] == "PAC mensile"

    list_resp = await client.get("/api/v1/assets", headers=_auth_headers(token))
    assert len(list_resp.json()) == 1


async def test_asset_duplicate_symbol_rejected(client):
    token = await _register(client, "asset-dup@example.com")
    await _create_asset(client, token, symbol="VWCE")
    response = await client.post(
        "/api/v1/assets",
        json={"name": "Altro nome", "symbol": "vwce", "asset_type": "etf", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


async def test_asset_with_no_movements_can_be_deleted_but_referenced_one_cannot(client):
    token = await _register(client, "asset-delete@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    free_asset = await _create_asset(client, token, symbol="FREE", name="Senza movimenti")
    delete_free = await client.delete(f"/api/v1/assets/{free_asset}", headers=_auth_headers(token))
    assert delete_free.status_code == 204

    txn_resp = await _create_investment_transaction(client, token, account_id, asset_id=asset_id)
    assert txn_resp.status_code == 201, txn_resp.text

    delete_used = await client.delete(f"/api/v1/assets/{asset_id}", headers=_auth_headers(token))
    assert delete_used.status_code == 400


# --- Investment transactions + posizione derivata ----------------------------


async def test_buy_creates_position(client):
    token = await _register(client, "buy-position@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    response = await _create_investment_transaction(client, token, account_id, asset_id=asset_id)
    assert response.status_code == 201, response.text

    positions = await client.get(
        "/api/v1/positions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    assert len(positions.json()) == 1
    position = positions.json()[0]
    assert position["quantity"] == "10.0000000000"
    assert position["average_cost"] == "100.000000"


async def test_two_buys_produce_weighted_average_cost_in_position(client):
    token = await _register(client, "weighted-position@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    await _create_investment_transaction(
        client, token, account_id, asset_id=asset_id, quantity="10", price="100.00", amount="-1000.00"
    )
    await _create_investment_transaction(
        client,
        token,
        account_id,
        asset_id=asset_id,
        trade_date="2026-02-01",
        quantity="10",
        price="120.00",
        amount="-1200.00",
    )

    positions = await client.get(
        "/api/v1/positions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    position = positions.json()[0]
    assert position["quantity"] == "20.0000000000"
    assert position["average_cost"] == "110.000000"


async def test_sell_reduces_quantity_and_realizes_pl(client):
    token = await _register(client, "sell-position@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    await _create_investment_transaction(client, token, account_id, asset_id=asset_id)
    sell_resp = await _create_investment_transaction(
        client,
        token,
        account_id,
        asset_id=asset_id,
        trade_date="2026-02-01",
        type="sell",
        quantity="4",
        price="150.00",
        amount="600.00",
    )
    assert sell_resp.status_code == 201, sell_resp.text

    positions = await client.get(
        "/api/v1/positions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    position = positions.json()[0]
    assert position["quantity"] == "6.0000000000"
    assert position["realized_pl"] == "200.00"


async def test_sell_exceeding_quantity_is_rejected(client):
    token = await _register(client, "oversell@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    await _create_investment_transaction(client, token, account_id, asset_id=asset_id)
    oversell = await _create_investment_transaction(
        client,
        token,
        account_id,
        asset_id=asset_id,
        trade_date="2026-02-01",
        type="sell",
        quantity="999",
        price="150.00",
        amount="1000.00",
    )
    assert oversell.status_code == 400

    # La posizione non deve essere stata alterata dal tentativo rifiutato
    # (l'intera operazione e' stata rollback-ata).
    positions = await client.get(
        "/api/v1/positions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    assert positions.json()[0]["quantity"] == "10.0000000000"


async def test_fully_closed_position_shows_zero_not_scientific_notation(client):
    """Regressione su dati reali: acquistare e poi rivendere l'intera
    quantita' (7 - 7) azzera esattamente la posizione. In Python
    `Decimal('7.0000000000') - Decimal('7.0000000000')` preserva
    l'esponente degli operandi e produce `Decimal('0E-10')` — stesso valore
    matematico di zero, ma la sua resa testuale di default e' notazione
    scientifica, non "0.0000000000" (bug osservato in UI su una posizione
    chiusa)."""
    token = await _register(client, "closed-position@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    await _create_investment_transaction(
        client, token, account_id, asset_id=asset_id, quantity="7", price="69.142857", amount="-484.00"
    )
    await _create_investment_transaction(
        client,
        token,
        account_id,
        asset_id=asset_id,
        trade_date="2026-02-01",
        type="sell",
        quantity="7",
        price="68.527143",
        amount="479.69",
    )

    default_positions = await client.get(
        "/api/v1/positions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    assert default_positions.json() == []  # rework UX/design: only_open=True di default nasconde le posizioni chiuse

    positions = await client.get(
        "/api/v1/positions",
        params={"financial_account_id": account_id, "only_open": "false"},
        headers=_auth_headers(token),
    )
    position = positions.json()[0]
    assert position["quantity"] == "0.0000000000"
    assert position["average_cost"] == "0.000000"
    assert position["realized_pl"] == "-4.31"


async def test_deleting_investment_transaction_recomputes_position(client):
    token = await _register(client, "delete-recompute@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    first = await _create_investment_transaction(client, token, account_id, asset_id=asset_id)
    txn_id = first.json()["id"]
    await _create_investment_transaction(
        client,
        token,
        account_id,
        asset_id=asset_id,
        trade_date="2026-02-01",
        quantity="5",
        price="200.00",
        amount="-1000.00",
    )

    delete_resp = await client.delete(
        f"/api/v1/investment-transactions/{txn_id}", headers=_auth_headers(token)
    )
    assert delete_resp.status_code == 204

    positions = await client.get(
        "/api/v1/positions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    position = positions.json()[0]
    assert position["quantity"] == "5.0000000000"
    assert position["average_cost"] == "200.000000"


async def test_deleting_last_investment_transaction_removes_position(client):
    token = await _register(client, "delete-last@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    only = await _create_investment_transaction(client, token, account_id, asset_id=asset_id)
    txn_id = only.json()["id"]

    await client.delete(f"/api/v1/investment-transactions/{txn_id}", headers=_auth_headers(token))

    positions = await client.get(
        "/api/v1/positions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    assert positions.json() == []


async def test_investment_transaction_rejects_account_from_another_workspace(client):
    token_a = await _register(client, "itx-cross-a@example.com")
    token_b = await _register(client, "itx-cross-b@example.com")
    account_b = await _create_account(client, token_b)
    asset_a = await _create_asset(client, token_a)

    response = await _create_investment_transaction(client, token_a, account_b, asset_id=asset_a)
    assert response.status_code == 400


# --- Modifica manuale della posizione (onboarding senza storico) ------------


async def test_manual_position_edit_creates_adjustment_and_position(client):
    token = await _register(client, "manual-edit@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    response = await client.put(
        f"/api/v1/positions/by-account/{account_id}/asset/{asset_id}",
        json={"quantity": "120", "average_cost": "63.40"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["quantity"] == "120.0000000000"
    assert response.json()["average_cost"] == "63.400000"

    movements = await client.get(
        "/api/v1/investment-transactions",
        params={"financial_account_id": account_id, "asset_id": asset_id},
        headers=_auth_headers(token),
    )
    assert len(movements.json()) == 1
    assert movements.json()[0]["type"] == "opening" or movements.json()[0]["type"] == "adjustment"


async def test_manual_position_edit_on_top_of_existing_movements_writes_delta(client):
    token = await _register(client, "manual-edit-delta@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)

    await _create_investment_transaction(client, token, account_id, asset_id=asset_id)  # 10 @ 100

    response = await client.put(
        f"/api/v1/positions/by-account/{account_id}/asset/{asset_id}",
        json={"quantity": "8", "average_cost": "100"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == "8.0000000000"

    movements = await client.get(
        "/api/v1/investment-transactions",
        params={"financial_account_id": account_id, "asset_id": asset_id},
        headers=_auth_headers(token),
    )
    adjustment = next(m for m in movements.json() if m["type"] == "adjustment")
    assert adjustment["quantity"] == "-2.0000000000"


# --- Portfolio + conti associati ---------------------------------------------


async def test_portfolio_crud_and_account_association(client):
    token = await _register(client, "portfolio-crud@example.com")
    account_id = await _create_account(client, token)

    create_resp = await client.post(
        "/api/v1/portfolios",
        json={"name": "Investimenti", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    portfolio_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/accounts",
        json={"financial_account_id": account_id},
        headers=_auth_headers(token),
    )
    assert add_resp.status_code == 201, add_resp.text

    list_resp = await client.get(
        f"/api/v1/portfolios/{portfolio_id}/accounts", headers=_auth_headers(token)
    )
    assert len(list_resp.json()) == 1

    remove_resp = await client.delete(
        f"/api/v1/portfolios/{portfolio_id}/accounts/{account_id}", headers=_auth_headers(token)
    )
    assert remove_resp.status_code == 204

    list_after = await client.get(
        f"/api/v1/portfolios/{portfolio_id}/accounts", headers=_auth_headers(token)
    )
    assert list_after.json() == []


async def test_portfolio_rejects_account_from_another_workspace(client):
    token_a = await _register(client, "portfolio-cross-a@example.com")
    token_b = await _register(client, "portfolio-cross-b@example.com")
    account_b = await _create_account(client, token_b)

    create_resp = await client.post(
        "/api/v1/portfolios", json={"name": "Investimenti", "currency": "EUR"}, headers=_auth_headers(token_a)
    )
    portfolio_id = create_resp.json()["id"]

    add_resp = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/accounts",
        json={"financial_account_id": account_b},
        headers=_auth_headers(token_a),
    )
    assert add_resp.status_code == 400


async def test_portfolio_duplicate_name_rejected(client):
    token = await _register(client, "portfolio-dup@example.com")
    await client.post(
        "/api/v1/portfolios", json={"name": "Investimenti", "currency": "EUR"}, headers=_auth_headers(token)
    )
    dup_resp = await client.post(
        "/api/v1/portfolios", json={"name": "Investimenti", "currency": "EUR"}, headers=_auth_headers(token)
    )
    assert dup_resp.status_code == 400

"""Test degli endpoint di analytics del portfolio (milestone 09b):
valuation/allocation live, net-worth-history letto dagli snapshot (mai
ricalcolato al volo, DoD M09). Il grafico "Andamento del valore" di
Investimenti (`/analytics/performance`, redesign) invece ricostruisce lo
storico vero dal libro movimenti + storico prezzi
(`compute_historical_series`), non legge piu' dagli snapshot: a differenza
di uno snapshot congelato alla data di scrittura, riflette correttamente
anche un movimento inserito con data passata dopo il fatto.
"""
import uuid

from httpx import AsyncClient

from app.services.job_run_tracker import finish_run, start_run
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


async def test_strategy_breakdown_excludes_fully_closed_position(client):
    """Regressione: un asset comprato "una tantum" e poi rivenduto per
    intero non deve piu' contare nel totale "PAC vs Investimenti" — il
    disallineamento reale segnalato dall'utente rispetto a "Per tipo di
    strumento" (che vede solo le posizioni aperte)."""
    token = await _register(client, "pf-strategy-closed@example.com")
    account_id = await _create_account(client, token)
    open_id = await _create_asset(client, token, name="Aperta", symbol="OPEN", asset_type="stock")
    closed_id = await _create_asset(client, token, name="Chiusa", symbol="CLOSED", asset_type="stock")
    await _buy(client, token, account_id, open_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_id, closed_id, quantity="5", price="200.00", amount="-1000.00")
    await client.post(
        "/api/v1/investment-transactions",
        json={
            "financial_account_id": account_id,
            "asset_id": closed_id,
            "trade_date": "2026-02-01",
            "type": "sell",
            "quantity": "5",
            "price": "250.00",
            "amount": "1250.00",
            "currency": "EUR",
        },
        headers=_auth_headers(token),
    )

    response = await client.get("/api/v1/portfolios/analytics/allocation", headers=_auth_headers(token))
    body = response.json()
    by_strategy_total = sum(float(item["value"]) for item in body["by_strategy"])
    by_asset_type_total = sum(float(item["value"]) for item in body["by_asset_type"])
    assert by_strategy_total == by_asset_type_total == 1000.00


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


# --- Scope "unassigned" (redesign Investimenti: vista "Asset senza portfolio") --


async def test_valuation_unassigned_returns_only_accounts_not_in_any_portfolio(client):
    token = await _register(client, "pf-unassigned-valuation@example.com")
    account_in = await _create_account(client, token, name="Dentro un portfolio")
    account_out = await _create_account(client, token, name="Non raggruppato")
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_in, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_out, asset_id, quantity="5", price="100.00", amount="-500.00")

    portfolio = await client.post(
        "/api/v1/portfolios", json={"name": "Con un conto dentro", "currency": "EUR"}, headers=_auth_headers(token)
    )
    portfolio_id = portfolio.json()["id"]
    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/accounts",
        json={"financial_account_id": account_in},
        headers=_auth_headers(token),
    )

    unassigned = await client.get(
        "/api/v1/portfolios/analytics/valuation", params={"unassigned": "true"}, headers=_auth_headers(token)
    )
    assert unassigned.json()["cost_basis"] == "500.00"  # solo il conto non raggruppato


async def test_valuation_unassigned_is_zero_when_every_account_is_in_a_portfolio(client):
    token = await _register(client, "pf-unassigned-all-grouped@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)

    portfolio = await client.post(
        "/api/v1/portfolios", json={"name": "Tutto qui dentro", "currency": "EUR"}, headers=_auth_headers(token)
    )
    await client.post(
        f"/api/v1/portfolios/{portfolio.json()['id']}/accounts",
        json={"financial_account_id": account_id},
        headers=_auth_headers(token),
    )

    unassigned = await client.get(
        "/api/v1/portfolios/analytics/valuation", params={"unassigned": "true"}, headers=_auth_headers(token)
    )
    body = unassigned.json()
    assert body["cost_basis"] == "0.00"
    assert body["has_holdings"] is False


async def test_allocation_unassigned_excludes_accounts_in_a_portfolio(client):
    token = await _register(client, "pf-unassigned-allocation@example.com")
    account_in = await _create_account(client, token, name="Dentro un portfolio")
    account_out = await _create_account(client, token, name="Non raggruppato")
    asset_id = await _create_asset(client, token, name="Solo qui fuori", symbol="OUT")
    await _buy(client, token, account_in, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_out, asset_id, quantity="5", price="100.00", amount="-500.00")

    portfolio = await client.post(
        "/api/v1/portfolios", json={"name": "Con un conto dentro", "currency": "EUR"}, headers=_auth_headers(token)
    )
    await client.post(
        f"/api/v1/portfolios/{portfolio.json()['id']}/accounts",
        json={"financial_account_id": account_in},
        headers=_auth_headers(token),
    )

    unassigned = await client.get(
        "/api/v1/portfolios/analytics/allocation", params={"unassigned": "true"}, headers=_auth_headers(token)
    )
    body = unassigned.json()
    assert len(body["by_account"]) == 1
    assert body["by_account"][0]["value"] == "500.00"


async def test_performance_unassigned_returns_reconstructed_history(client):
    """A differenza dello storico via snapshot (mai scritto per questo
    pseudo-gruppo), la ricostruzione dal libro movimenti funziona per
    QUALSIASI scope, incluso "Asset senza portfolio"."""
    token = await _register(client, "pf-unassigned-performance@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)

    response = await client.get(
        "/api/v1/portfolios/analytics/performance", params={"unassigned": "true"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    points = response.json()["points"]
    assert len(points) >= 1
    assert points[-1]["cost_basis"] == "1000.00"


# --- Riepilogo per-portfolio in batch (redesign Investimenti, lista Panoramica) --


async def test_portfolio_summaries_empty_when_no_portfolio_exists(client):
    token = await _register(client, "pf-summary-empty@example.com")
    response = await client.get("/api/v1/portfolios/analytics/summary", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_portfolio_summaries_lists_every_portfolio_with_its_own_valuation(client):
    token = await _register(client, "pf-summary@example.com")
    account_a = await _create_account(client, token, name="Conto A")
    account_b = await _create_account(client, token, name="Conto B")
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_a, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_b, asset_id, quantity="5", price="100.00", amount="-500.00")

    portfolio_a = await client.post(
        "/api/v1/portfolios", json={"name": "Portfolio A", "currency": "EUR"}, headers=_auth_headers(token)
    )
    portfolio_b = await client.post(
        "/api/v1/portfolios", json={"name": "Portfolio B", "currency": "EUR"}, headers=_auth_headers(token)
    )
    await client.post(
        f"/api/v1/portfolios/{portfolio_a.json()['id']}/accounts",
        json={"financial_account_id": account_a},
        headers=_auth_headers(token),
    )
    await client.post(
        f"/api/v1/portfolios/{portfolio_b.json()['id']}/accounts",
        json={"financial_account_id": account_b},
        headers=_auth_headers(token),
    )

    response = await client.get("/api/v1/portfolios/analytics/summary", headers=_auth_headers(token))
    body = response.json()
    by_name = {item["name"]: item for item in body["items"]}
    assert set(by_name) == {"Portfolio A", "Portfolio B"}
    assert by_name["Portfolio A"]["cost_basis"] == "1000.00"
    assert by_name["Portfolio A"]["account_count"] == 1
    assert by_name["Portfolio B"]["cost_basis"] == "500.00"
    assert by_name["Portfolio B"]["account_count"] == 1


async def test_portfolio_summaries_portfolio_without_accounts_is_zero(client):
    token = await _register(client, "pf-summary-no-accounts@example.com")
    await client.post(
        "/api/v1/portfolios", json={"name": "Vuoto", "currency": "EUR"}, headers=_auth_headers(token)
    )

    response = await client.get("/api/v1/portfolios/analytics/summary", headers=_auth_headers(token))
    item = response.json()["items"][0]
    assert item["account_count"] == 0
    assert item["cost_basis"] == "0.00"
    assert item["has_holdings"] is False


# --- Valore/rendimento per singola posizione (redesign Investimenti, tabella Posizioni) --


async def test_positions_endpoint_returns_value_and_return_per_row(client):
    token = await _register(client, "pf-positions@example.com")
    account_id = await _create_account(client, token, name="Trade Republic")
    asset_id = await _create_asset(client, token, name="Vanguard FTSE All-World", symbol="VWCE")
    await _buy(client, token, account_id, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "120.00", "currency": "EUR"},
        headers=_auth_headers(token),
    )

    response = await client.get("/api/v1/portfolios/analytics/positions", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_market_data"] is True
    assert len(body["positions"]) == 1
    row = body["positions"][0]
    assert row["asset_label"] == "VWCE"
    assert row["account_label"] == "Trade Republic"
    assert row["market_value"] == "1200.00"
    assert row["unrealized_pl"] == "200.00"
    assert row["currency_native"] == "EUR"
    assert uuid.UUID(row["position_id"])


async def test_positions_endpoint_prefers_display_name_over_raw_asset_name(client, monkeypatch):
    """Regressione: la tabella Asset di un portfolio mostrava il nome grezzo
    del parser (spesso con suffissi di borsa tedeschi tipo "DL-,0001", vedi
    docstring di `AssetProfile.display_name`) invece del nome pulito gia'
    arricchito dal provider — stesso principio gia' corretto per GET
    /assets, mancava solo qui."""
    from app.marketdata.base import AssetProfile as ProviderAssetProfile

    async def fake_fetch_profile(self, asset):
        return ProviderAssetProfile(
            issuer=None, category=None, aum=None, distribution_policy=None,
            display_name="D-Wave Quantum Inc.",
        )

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_profile", fake_fetch_profile)

    token = await _register(client, "pf-positions-display-name@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token, name="D-WAVE QUATUM DL-,0001", symbol="QBTS")
    await _buy(client, token, account_id, asset_id)

    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )
    await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))

    response = await client.get("/api/v1/portfolios/analytics/positions", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    row = response.json()["positions"][0]
    assert row["asset_label"] == "D-Wave Quantum Inc."
    assert uuid.UUID(row["financial_account_id"])


async def test_positions_endpoint_excludes_closed_positions_by_default(client):
    token = await _register(client, "pf-positions-closed@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await client.post(
        "/api/v1/investment-transactions",
        json={
            "financial_account_id": account_id,
            "asset_id": asset_id,
            "trade_date": "2026-02-01",
            "type": "sell",
            "quantity": "10",
            "price": "150.00",
            "amount": "1500.00",
            "currency": "EUR",
        },
        headers=_auth_headers(token),
    )

    default_response = await client.get("/api/v1/portfolios/analytics/positions", headers=_auth_headers(token))
    assert default_response.json()["positions"] == []

    with_closed = await client.get(
        "/api/v1/portfolios/analytics/positions", params={"include_closed": "true"}, headers=_auth_headers(token)
    )
    rows = with_closed.json()["positions"]
    assert len(rows) == 1
    assert float(rows[0]["quantity"]) == 0
    assert rows[0]["realized_pl"] == "500.00"


async def test_positions_endpoint_scoped_to_portfolio(client):
    token = await _register(client, "pf-positions-scoped@example.com")
    account_in = await _create_account(client, token, name="Dentro")
    account_out = await _create_account(client, token, name="Fuori")
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_in, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_out, asset_id, quantity="5", price="100.00", amount="-500.00")

    portfolio = await client.post(
        "/api/v1/portfolios", json={"name": "Solo dentro", "currency": "EUR"}, headers=_auth_headers(token)
    )
    await client.post(
        f"/api/v1/portfolios/{portfolio.json()['id']}/accounts",
        json={"financial_account_id": account_in},
        headers=_auth_headers(token),
    )

    scoped = await client.get(
        "/api/v1/portfolios/analytics/positions",
        params={"portfolio_id": portfolio.json()["id"]},
        headers=_auth_headers(token),
    )
    rows = scoped.json()["positions"]
    assert len(rows) == 1
    assert rows[0]["account_label"] == "Dentro"


async def test_positions_endpoint_flags_missing_fx_rate_without_hiding_it(client):
    token = await _register(client, "pf-positions-fx@example.com")
    account_id = await _create_account(client, token, currency="USD")
    asset_id = await _create_asset(client, token, currency="USD")
    await _buy(
        client, token, account_id, asset_id, quantity="10", price="100.00", amount="-1000.00", currency="USD"
    )
    # Nessun tasso USD->EUR inserito: la posizione non puo' essere convertita.

    response = await client.get("/api/v1/portfolios/analytics/positions", headers=_auth_headers(token))
    body = response.json()
    assert body["positions"] == []
    assert body["has_missing_fx_rate"] is True


async def test_positions_endpoint_unassigned_scope(client):
    token = await _register(client, "pf-positions-unassigned@example.com")
    account_in = await _create_account(client, token, name="Dentro un portfolio")
    account_out = await _create_account(client, token, name="Non raggruppato")
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_in, asset_id, quantity="10", price="100.00", amount="-1000.00")
    await _buy(client, token, account_out, asset_id, quantity="5", price="100.00", amount="-500.00")

    portfolio = await client.post(
        "/api/v1/portfolios", json={"name": "Con un conto dentro", "currency": "EUR"}, headers=_auth_headers(token)
    )
    await client.post(
        f"/api/v1/portfolios/{portfolio.json()['id']}/accounts",
        json={"financial_account_id": account_in},
        headers=_auth_headers(token),
    )

    response = await client.get(
        "/api/v1/portfolios/analytics/positions", params={"unassigned": "true"}, headers=_auth_headers(token)
    )
    rows = response.json()["positions"]
    assert len(rows) == 1
    assert rows[0]["account_label"] == "Non raggruppato"


# --- Rendimento per asset (card "Rendimento" del dettaglio, sistema di valute) --


async def test_asset_valuation_uses_market_price_when_available(client):
    token = await _register(client, "asset-valuation-price@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)
    await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "120.00", "currency": "EUR"},
        headers=_auth_headers(token),
    )

    response = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
    body = response.json()
    assert body["market_value"] == "1200.00"
    assert body["unrealized_pl"] == "200.00"
    assert body["has_market_data"] is True
    assert body["has_missing_fx_rate"] is False
    assert body["price"] == "120.00"
    assert body["price_native"] == "120.000000"
    assert body["price_native_currency"] == "EUR"


async def test_asset_valuation_converts_price_in_different_currency(client):
    """Regressione: prima di questo endpoint, il rendimento sul dettaglio
    asset spariva (mostrava "—") quando il prezzo era in una valuta diversa
    da quella della posizione (es. ISIN estero quotato in USD ma comprato
    in EUR) — l'utente lo considera un dato troppo importante per sparire,
    quindi ora si converte sempre tramite `fx_rates` invece di degradare."""
    token = await _register(client, "asset-valuation-fx@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token, currency="EUR")
    await _buy(client, token, account_id, asset_id, quantity="10", price="100.00", amount="-1000.00", currency="EUR")
    # Prezzo quotato dal provider in USD (caso reale: ISIN estero), non EUR.
    await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "120.00", "currency": "USD"},
        headers=_auth_headers(token),
    )
    await client.put(
        "/api/v1/currencies/rates",
        json={"from_currency": "USD", "to_currency": "EUR", "rate_date": "2026-08-01", "rate": "0.90"},
        headers=_auth_headers(token),
    )

    # L'endpoint non espone `as_of` (sempre oggi lato server, vedi
    # get_asset_valuation): il prezzo/tasso datati 2026-08-01 restano
    # comunque "l'ultimo disponibile non piu' recente di oggi".
    response = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
    body = response.json()
    assert body["has_market_data"] is True
    assert body["market_value"] == "1080.00"  # 10 * 120 USD * 0.90
    assert body["unrealized_pl"] == "80.00"  # 1080 - 1000
    assert body["has_missing_fx_rate"] is False
    assert body["price"] == "108.00"  # 120 USD * 0.90, convertito
    assert body["price_native"] == "120.000000"
    assert body["price_native_currency"] == "USD"


async def test_asset_valuation_falls_back_to_cost_when_price_fx_rate_missing(client):
    token = await _register(client, "asset-valuation-fx-missing@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token, currency="EUR")
    await _buy(client, token, account_id, asset_id, quantity="10", price="100.00", amount="-1000.00", currency="EUR")
    await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "120.00", "currency": "JPY"},
        headers=_auth_headers(token),
    )
    # Nessun tasso JPY->EUR inserito: la conversione non e' possibile.

    response = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
    body = response.json()
    assert body["has_market_data"] is False
    assert body["market_value"] == body["cost_basis"] == "1000.00"  # fallback onesto a costo storico
    assert body["unrealized_pl"] == "0.00"
    assert body["price"] is None  # nessun tasso per convertirlo
    assert body["price_native"] == "120.000000"
    assert body["price_native_currency"] == "JPY"


async def test_asset_valuation_with_no_positions_returns_zeroes(client):
    token = await _register(client, "asset-valuation-empty@example.com")
    asset_id = await _create_asset(client, token)

    response = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == "0"
    assert body["market_value"] == "0.00"
    assert body["has_market_data"] is True
    assert body["price"] is None
    assert body["price_native"] is None


async def test_net_worth_history_reads_from_snapshots(client):
    token = await _register(client, "pf-performance@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = me.json()["workspace_id"]
    user_id = me.json()["id"]
    await write_snapshot_for_workspace(None, workspace_id, user_id)

    # Un secondo acquisto DOPO lo snapshot non deve alterare il punto
    # storico gia' scritto (DoD: "non ricalcolato da zero ogni volta") — per
    # il Patrimonio generale (liquidita'+debiti+investimenti), che resta su
    # snapshot. Il grafico "Andamento del valore" di Investimenti invece
    # ricostruisce dal libro movimenti: vedi
    # test_performance_reflects_a_backdated_transaction_immediately.
    await _buy(
        client, token, account_id, asset_id, trade_date="2026-06-01", quantity="5", price="200.00", amount="-1000.00"
    )

    net_worth = await client.get("/api/v1/analytics/net-worth-history", headers=_auth_headers(token))
    nw_points = net_worth.json()["points"]
    assert len(nw_points) == 1
    assert nw_points[0]["investments"] == "1000.00"


async def test_performance_reflects_a_backdated_transaction_immediately(client):
    """A differenza dello storico "Patrimonio" (via snapshot congelato),
    l'Andamento del valore di Investimenti ricostruisce sempre dal libro
    movimenti corrente: un acquisto inserito con data passata si riflette
    subito, senza aspettare che un nuovo snapshot venga scritto."""
    token = await _register(client, "pf-performance-backdated@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _buy(client, token, account_id, asset_id)
    await _buy(
        client, token, account_id, asset_id, trade_date="2026-06-01", quantity="5", price="200.00", amount="-1000.00"
    )

    performance = await client.get("/api/v1/portfolios/analytics/performance", headers=_auth_headers(token))
    points = performance.json()["points"]
    assert len(points) >= 1
    assert points[-1]["cost_basis"] == "2000.00"


# --- Stato persistente del ricalcolo snapshot (gap UX, non un toast) ------


async def test_snapshot_status_is_null_when_never_run(client):
    token = await _register(client, "pf-snapshot-status-null@example.com")
    response = await client.get("/api/v1/portfolios/snapshots/status", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() is None


async def test_snapshot_status_reflects_last_run_and_survives_a_page_reload(client):
    token = await _register(client, "pf-snapshot-status@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = me.json()["workspace_id"], me.json()["id"]

    await write_snapshot_for_workspace(None, workspace_id, user_id)

    response = await client.get("/api/v1/portfolios/snapshots/status", headers=_auth_headers(token))
    body = response.json()
    assert body["status"] == "success"
    assert body["finished_at"] is not None
    assert "0 portfolio" in body["message"]  # nessun portfolio nominato creato in questo test


async def test_snapshot_rebuild_does_not_enqueue_a_second_job_while_one_is_running(client, monkeypatch):
    import app.api.v1.portfolios as portfolios_module

    calls = []

    async def fake_enqueue(workspace_id, user_id):
        calls.append((workspace_id, user_id))
        return "fake-job-id"

    monkeypatch.setattr(portfolios_module, "enqueue_snapshot_rebuild", fake_enqueue)

    token = await _register(client, "pf-rebuild-no-double-enqueue@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = uuid.UUID(me.json()["workspace_id"]), uuid.UUID(me.json()["id"])

    await start_run(workspace_id, user_id, "snapshot_rebuild")

    response = await client.post("/api/v1/portfolios/snapshots/rebuild", headers=_auth_headers(token))
    assert response.status_code == 202
    assert calls == []


async def test_snapshot_rebuild_enqueues_again_after_a_previous_run_completed(client, monkeypatch):
    """Stessa regressione di `test_refresh_enqueues_again_after_a_previous_run_completed`
    ma per il ricalcolo snapshot."""
    import app.api.v1.portfolios as portfolios_module

    calls = []

    async def fake_enqueue(workspace_id, user_id):
        calls.append((workspace_id, user_id))
        return "fake-job-id"

    monkeypatch.setattr(portfolios_module, "enqueue_snapshot_rebuild", fake_enqueue)

    token = await _register(client, "pf-rebuild-reenqueue@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = uuid.UUID(me.json()["workspace_id"]), uuid.UUID(me.json()["id"])

    await start_run(workspace_id, user_id, "snapshot_rebuild")
    await finish_run(workspace_id, user_id, "snapshot_rebuild", success=True, message="ok")

    response = await client.post("/api/v1/portfolios/snapshots/rebuild", headers=_auth_headers(token))
    assert response.status_code == 202
    assert len(calls) == 1

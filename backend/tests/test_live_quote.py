"""Test per la live-quote del dettaglio asset (docs/SPEC_STOCK_PRICE.md):
cache Redis con TTL, anti cache-stampede, fallback onesto quando il
provider non risponde — e verifica che nulla di tutto questo scriva mai
`asset_prices` (il prezzo daily canonico resta invariato dalla sola
apertura di una pagina). Include anche il filtro "solo posizioni aperte"
del job di refresh bulk, stesso documento.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.marketdata.base import MarketDataProviderError, PricePoint, Quote
from app.models.asset_price_quote import AssetPriceQuote
from app.models.user import User
from app.worker.jobs.market_data import refresh_market_data_for_workspace


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_asset(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Vanguard FTSE All-World", "symbol": "VWCE", "asset_type": "etf", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/assets", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_account(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/accounts", json=payload, headers=_auth_headers(token))
    return response.json()["id"]


async def _activate_yahoo_profile(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {"name": "Yahoo", "provider": "yahoo"}
    payload.update(overrides)
    create_resp = await client.post(
        "/api/v1/settings/market-data/profiles", json=payload, headers=_auth_headers(token)
    )
    assert create_resp.status_code == 201, create_resp.text
    profile = create_resp.json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profile['id']}/activate", headers=_auth_headers(token)
    )
    return profile


async def test_live_quote_cache_hit_avoids_second_provider_call(client, monkeypatch):
    calls = []

    async def fake_fetch_quote(self, asset):
        calls.append(1)
        return Quote(price=Decimal("123.45"), currency="EUR", as_of=date.today())

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "live-quote-cache-hit@example.com")
    asset_id = await _create_asset(client, token)
    await _activate_yahoo_profile(client, token, detail_refresh_interval_seconds=30)

    first = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
    second = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))

    assert first.status_code == 200 and second.status_code == 200
    assert len(calls) == 1  # secondo giro servito dalla cache Redis, nessun secondo fetch
    assert first.json()["price_is_live"] is True
    assert first.json()["price_is_stale"] is False
    assert Decimal(first.json()["price_native"]) == Decimal("123.45")


async def test_live_quote_cache_miss_persists_intraday_observation(client, monkeypatch):
    async def fake_fetch_quote(self, asset):
        return Quote(price=Decimal("50.00"), currency="EUR", as_of=date.today())

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "live-quote-persist@example.com")
    asset_id = await _create_asset(client, token)
    await _activate_yahoo_profile(client, token)

    response = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
    assert response.status_code == 200
    assert Decimal(response.json()["price_native"]) == Decimal("50.00")

    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.email == "live-quote-persist@example.com"))).scalar_one()
    async with rls_session(user.id) as db:
        rows = (
            await db.execute(select(AssetPriceQuote).where(AssetPriceQuote.asset_id == uuid.UUID(asset_id)))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].price == Decimal("50.000000")
    assert rows[0].source == "yahoo"


async def test_live_quote_never_writes_daily_asset_prices(client, monkeypatch):
    """Regola esplicita SPEC: la visita della pagina di dettaglio non deve
    mai scrivere `asset_prices` (mai "l'ultimo prezzo visto dalla UI")."""

    async def fake_fetch_quote(self, asset):
        return Quote(price=Decimal("77.00"), currency="EUR", as_of=date.today())

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "live-quote-no-daily-write@example.com")
    asset_id = await _create_asset(client, token)
    await _activate_yahoo_profile(client, token)

    for _ in range(3):
        response = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
        assert response.status_code == 200

    prices_resp = await client.get(f"/api/v1/assets/{asset_id}/prices", headers=_auth_headers(token))
    assert prices_resp.json() == []


async def test_live_quote_provider_failure_falls_back_to_daily_price_marked_stale(client, monkeypatch):
    async def failing_fetch_quote(self, asset):
        raise MarketDataProviderError("Yahoo non raggiungibile")

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", failing_fetch_quote)

    token = await _register(client, "live-quote-provider-down@example.com")
    asset_id = await _create_asset(client, token)
    await _activate_yahoo_profile(client, token)

    put_resp = await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": str(date.today()), "price": "42.00", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert put_resp.status_code == 200, put_resp.text

    response = await client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token))
    assert response.status_code == 200  # mai un 500 solo perche' il provider non risponde
    assert Decimal(response.json()["price_native"]) == Decimal("42.00")
    assert response.json()["price_is_stale"] is True


async def test_live_quote_concurrent_requests_trigger_a_single_provider_call(client, monkeypatch):
    """Anti cache-stampede (SPEC Caso 1/2): due richieste concorrenti sullo
    stesso asset entro la finestra di scadenza NON devono produrre due fetch
    reali al provider."""
    calls = []

    async def slow_fetch_quote(self, asset):
        calls.append(1)
        await asyncio.sleep(0.3)
        return Quote(price=Decimal("10.00"), currency="EUR", as_of=date.today())

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", slow_fetch_quote)

    token = await _register(client, "live-quote-stampede@example.com")
    asset_id = await _create_asset(client, token)
    await _activate_yahoo_profile(client, token)

    responses = await asyncio.gather(
        client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token)),
        client.get(f"/api/v1/assets/{asset_id}/valuation", headers=_auth_headers(token)),
    )
    assert all(r.status_code == 200 for r in responses)
    assert len(calls) == 1


async def test_market_data_profile_rejects_refresh_interval_below_floor(client):
    token = await _register(client, "live-quote-floor@example.com")
    response = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Yahoo", "provider": "yahoo", "detail_refresh_interval_seconds": 1},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_market_data_profile_defaults_refresh_intervals_when_omitted(client):
    token = await _register(client, "live-quote-defaults@example.com")
    response = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Yahoo", "provider": "yahoo"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    assert response.json()["portfolio_refresh_interval_seconds"] == 900
    assert response.json()["detail_refresh_interval_seconds"] == 15


async def test_live_quote_with_open_position_does_not_break_rls_for_the_rest_of_the_request(client, monkeypatch):
    """Regressione: un cache-miss reale (fetch + persist in asset_price_quotes)
    per un asset con una posizione APERTA innescava un `db.commit()` a meta'
    richiesta (dentro live_quote_service), che faceva scadere l'identita' RLS
    (`SET LOCAL app.current_user_id`) per la query `Position` successiva
    dentro `portfolio_analytics.get_asset_valuation` — 500 "invalid input
    syntax for type uuid: ''" (osservato in QA manuale con AAPL/Yahoo reali,
    MAI riprodotto dagli altri test perche' nessuno creava una posizione
    aperta reale per l'asset testato: senza righe in `positions`, la RLS non
    veniva mai valutata davvero)."""

    async def fake_fetch_quote(self, asset):
        return Quote(price=Decimal("123.45"), currency="EUR", as_of=date.today())

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "live-quote-open-position-rls@example.com")
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    buy_resp = await client.post(
        "/api/v1/investment-transactions",
        json={
            "financial_account_id": account_id,
            "trade_date": "2026-01-15",
            "type": "buy",
            "quantity": "10",
            "price": "100.00",
            "amount": "-1000.00",
            "currency": "EUR",
            "asset_id": asset_id,
        },
        headers=_auth_headers(token),
    )
    assert buy_resp.status_code == 201, buy_resp.text
    await _activate_yahoo_profile(client, token)

    response = await client.get(
        f"/api/v1/assets/{asset_id}/valuation?currency=EUR", headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_market_data"] is True


async def test_intraday_chart_falls_back_to_full_fetch_when_only_a_few_quotes_accumulated(client, monkeypatch):
    """Regressione: la cache intraday considerava "sufficiente" un unico
    punto recente (freschezza) senza controllare quanti punti ci fossero
    davvero — un utente che ha appena aperto la pagina (2-3 osservazioni
    dal polling della live-quote) vedeva un grafico "1G" con 2-3 punti
    invece dell'intera sessione che Yahoo restituirebbe con un fetch pieno
    (osservato in QA manuale). Sotto `_INTRADAY_MIN_POINTS` deve sempre
    ricadere sul fetch live completo."""
    history_calls = []

    async def fake_fetch_quote(self, asset):
        return Quote(price=Decimal("10.00"), currency="EUR", as_of=date.today())

    async def fake_fetch_history(self, asset, preset):
        history_calls.append(preset)
        now = datetime.now(timezone.utc)
        return [PricePoint(at=now - timedelta(minutes=i), price=Decimal("10.00")) for i in range(50)]

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_history", fake_fetch_history)

    token = await _register(client, "intraday-min-points@example.com")
    asset_id = await _create_asset(client, token)
    await _activate_yahoo_profile(client, token)

    # Simula "solo 2 osservazioni accumulate finora" (molto sotto la soglia
    # minima) inserendole direttamente, come farebbe live_quote_service dopo
    # un paio di poll ravvicinati.
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = me.json()["workspace_id"]
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.email == "intraday-min-points@example.com"))).scalar_one()
    async with rls_session(user.id) as db:
        now = datetime.now(timezone.utc)
        for i in range(2):
            db.add(
                AssetPriceQuote(
                    workspace_id=workspace_id,
                    asset_id=uuid.UUID(asset_id),
                    quoted_at=now - timedelta(seconds=i * 10),
                    price=Decimal("10.00"),
                    currency="EUR",
                    source="yahoo",
                )
            )
        await db.commit()

    response = await client.get(f"/api/v1/assets/{asset_id}/price-history?preset=1G", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    assert history_calls == ["1G"]  # copertura insufficiente (2 punti) -> fetch pieno, non la cache sparsa
    assert len(response.json()["points"]) == 50


async def test_intraday_chart_falls_back_to_full_fetch_when_points_cluster_in_a_narrow_window(client, monkeypatch):
    """Regressione: il solo conteggio dei punti non basta — 48 osservazioni
    raccolte in soli 9 minuti di polling ravvicinato superavano
    `_INTRADAY_MIN_POINTS` pur non rappresentando affatto "la giornata"
    (osservato in QA manuale con AAPL/Yahoo reali: un grafico ancora
    stretto su una manciata di minuti, solo con piu' punti dentro). Serve
    anche che l'intervallo COPERTO dalle osservazioni sia gia' ampio
    (`_INTRADAY_MIN_SPAN_HOURS`), altrimenti si ricade sempre sul fetch live
    completo."""
    history_calls = []

    async def fake_fetch_quote(self, asset):
        return Quote(price=Decimal("10.00"), currency="EUR", as_of=date.today())

    async def fake_fetch_history(self, asset, preset):
        history_calls.append(preset)
        now = datetime.now(timezone.utc)
        return [PricePoint(at=now - timedelta(minutes=i), price=Decimal("10.00")) for i in range(50)]

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_history", fake_fetch_history)

    token = await _register(client, "intraday-narrow-span@example.com")
    asset_id = await _create_asset(client, token)
    await _activate_yahoo_profile(client, token)

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = me.json()["workspace_id"]
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.email == "intraday-narrow-span@example.com"))).scalar_one()
    async with rls_session(user.id) as db:
        now = datetime.now(timezone.utc)
        # 48 punti (ben sopra _INTRADAY_MIN_POINTS=20) ma tutti entro una
        # finestra di soli 9 minuti — esattamente il caso reale osservato.
        for i in range(48):
            db.add(
                AssetPriceQuote(
                    workspace_id=workspace_id,
                    asset_id=uuid.UUID(asset_id),
                    quoted_at=now - timedelta(seconds=i * 11),
                    price=Decimal("10.00"),
                    currency="EUR",
                    source="yahoo",
                )
            )
        await db.commit()

    response = await client.get(f"/api/v1/assets/{asset_id}/price-history?preset=1G", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    assert history_calls == ["1G"]  # tanti punti ma finestra stretta -> fetch pieno comunque
    assert len(response.json()["points"]) == 50


async def test_refresh_workspace_only_fetches_assets_with_open_positions(client, monkeypatch):
    """docs/SPEC_STOCK_PRICE.md: il job bulk non deve scaricare prezzi per
    asset senza alcuna posizione ancora aperta."""
    fetched_symbols = []

    async def fake_fetch_quote(self, asset):
        fetched_symbols.append(asset.symbol)
        return Quote(price=Decimal("1.00"), currency="EUR", as_of=date.today())

    async def fake_fetch_fx_rate(self, from_currency, to_currency):
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_rate", fake_fetch_fx_rate)

    token = await _register(client, "refresh-open-positions@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = me.json()["workspace_id"], me.json()["id"]

    account_id = await _create_account(client, token)
    held_asset_id = await _create_asset(client, token, symbol="HELD")
    unheld_asset_id = await _create_asset(client, token, symbol="UNHELD")

    buy_resp = await client.post(
        "/api/v1/investment-transactions",
        json={
            "financial_account_id": account_id,
            "trade_date": "2026-01-15",
            "type": "buy",
            "quantity": "10",
            "price": "100.00",
            "amount": "-1000.00",
            "currency": "EUR",
            "asset_id": held_asset_id,
        },
        headers=_auth_headers(token),
    )
    assert buy_resp.status_code == 201, buy_resp.text

    await _activate_yahoo_profile(client, token)

    await refresh_market_data_for_workspace(None, workspace_id, user_id)

    assert fetched_symbols == ["HELD"]

    held_prices = await client.get(f"/api/v1/assets/{held_asset_id}/prices", headers=_auth_headers(token))
    unheld_prices = await client.get(f"/api/v1/assets/{unheld_asset_id}/prices", headers=_auth_headers(token))
    assert len(held_prices.json()) == 1
    assert unheld_prices.json() == []

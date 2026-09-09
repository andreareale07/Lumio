"""Test API dei profili MarketDataProvider e dei prezzi asset (milestone
09b) — stesso pattern di `test_portfolio_api.py`.
"""
import uuid
from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from app.services.job_run_tracker import finish_run, start_run
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
    payload = {"name": "Conto Test", "account_type": "checking", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/accounts", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Profili ------------------------------------------------------------


async def test_market_data_profile_crud(client):
    token = await _register(client, "md-crud@example.com")

    create_resp = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    profile_id = create_resp.json()["id"]
    assert create_resp.json()["is_active"] is False
    assert create_resp.json()["api_key_set"] is False

    update_resp = await client.patch(
        f"/api/v1/settings/market-data/profiles/{profile_id}",
        json={"name": "Manuale (aggiornato)"},
        headers=_auth_headers(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Manuale (aggiornato)"

    list_resp = await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    assert len(list_resp.json()) == 1


async def test_custom_provider_requires_endpoint_and_price_field(client):
    token = await _register(client, "md-custom-validation@example.com")

    missing_endpoint = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Alpha Vantage", "provider": "custom"},
        headers=_auth_headers(token),
    )
    assert missing_endpoint.status_code == 400

    missing_price_field = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Alpha Vantage", "provider": "custom", "endpoint": "https://example.invalid/{symbol}"},
        headers=_auth_headers(token),
    )
    assert missing_price_field.status_code == 400

    ok = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={
            "name": "Alpha Vantage",
            "provider": "custom",
            "endpoint": "https://example.invalid/{symbol}",
            "price_field": "price",
            "api_key": "secret-key",
        },
        headers=_auth_headers(token),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["api_key_set"] is True


async def test_activate_profile_deactivates_others(client):
    token = await _register(client, "md-activate@example.com")

    manual = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    stooq = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Stooq", "provider": "stooq"},
        headers=_auth_headers(token),
    )
    manual_id, stooq_id = manual.json()["id"], stooq.json()["id"]

    await client.post(f"/api/v1/settings/market-data/profiles/{manual_id}/activate", headers=_auth_headers(token))
    activate_resp = await client.post(
        f"/api/v1/settings/market-data/profiles/{stooq_id}/activate", headers=_auth_headers(token)
    )
    assert activate_resp.json()["is_active"] is True

    list_resp = await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    active = [p for p in list_resp.json() if p["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == stooq_id


async def test_deactivate_all_disables_market_data(client):
    token = await _register(client, "md-deactivate@example.com")
    created = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    profile_id = created.json()["id"]
    await client.post(f"/api/v1/settings/market-data/profiles/{profile_id}/activate", headers=_auth_headers(token))

    deactivate_resp = await client.post("/api/v1/settings/market-data/deactivate", headers=_auth_headers(token))
    assert deactivate_resp.status_code == 204

    list_resp = await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    assert all(not p["is_active"] for p in list_resp.json())


async def test_test_connection_on_manual_profile_always_succeeds(client):
    token = await _register(client, "md-test-manual@example.com")
    created = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    profile_id = created.json()["id"]

    test_resp = await client.post(
        f"/api/v1/settings/market-data/profiles/{profile_id}/test", headers=_auth_headers(token)
    )
    assert test_resp.status_code == 200
    assert test_resp.json()["success"] is True


async def test_draft_test_connection_reports_missing_endpoint_without_error(client):
    token = await _register(client, "md-test-draft@example.com")
    response = await client.post(
        "/api/v1/settings/market-data/test",
        json={"provider": "custom"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["success"] is False


# --- Prezzi asset (SPEC §38 "dati manuali") --------------------------------


async def test_manual_asset_price_upsert_and_list(client):
    token = await _register(client, "md-price@example.com")
    asset_id = await _create_asset(client, token)

    create_resp = await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "100.50", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert create_resp.status_code == 200, create_resp.text
    assert create_resp.json()["source"] == "manual"
    assert create_resp.json()["price"] == "100.500000"

    # Stesso giorno: sovrascrive, non duplica.
    overwrite_resp = await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "101.00", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert overwrite_resp.status_code == 200

    list_resp = await client.get(f"/api/v1/assets/{asset_id}/prices", headers=_auth_headers(token))
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["price"] == "101.000000"


async def test_asset_price_rejects_asset_from_another_workspace(client):
    token_a = await _register(client, "md-price-cross-a@example.com")
    token_b = await _register(client, "md-price-cross-b@example.com")
    asset_b = await _create_asset(client, token_b)

    response = await client.put(
        f"/api/v1/assets/{asset_b}/prices",
        json={"price_date": "2026-08-01", "price": "100.00", "currency": "EUR"},
        headers=_auth_headers(token_a),
    )
    assert response.status_code == 404


# --- Refresh tassi di cambio (sistema di valute) ---------------------------


async def test_refresh_updates_fx_rates_for_foreign_currency_account(client, monkeypatch):
    from app.marketdata.base import FxQuote

    calls = []

    async def fake_fetch_fx_rate(self, from_currency, to_currency):
        calls.append((from_currency, to_currency))
        return FxQuote(rate=Decimal("0.92"), as_of=date(2026, 8, 17))

    async def fake_fetch_fx_history(self, from_currency, to_currency, preset):
        return []  # storico non rilevante per questo test, vedi test dedicato al backfill

    async def fake_fetch_quote(self, asset):
        return None  # nessun asset in questo test, solo la parte FX

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_rate", fake_fetch_fx_rate)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_history", fake_fetch_fx_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-fx-refresh@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = me.json()["workspace_id"], me.json()["id"]
    # Conto in USD, workspace di default a base_currency EUR (backfill
    # migration): unica valuta "straniera" effettivamente in uso.
    await _create_account(client, token, currency="USD")

    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    await refresh_market_data_for_workspace(None, workspace_id, user_id)

    assert calls == [("USD", "EUR")]  # solo la valuta effettivamente in uso, non tutte le combinazioni

    from app.db.base import async_session_factory
    from app.services.fx_rate_service import get_rate

    async with async_session_factory() as db:
        rate = await get_rate(db, "USD", "EUR", date(2026, 8, 17))
    assert rate == Decimal("0.92")


async def test_refresh_updates_fx_rates_for_currency_only_seen_in_asset_prices(client, monkeypatch):
    """Regressione bug reale (Metaplanet): un asset registrato in EUR
    (valuta con cui l'utente l'ha comprato) ma quotato da Yahoo in JPY non
    rendeva mai JPY "in uso" (la vecchia logica guardava solo `Asset.
    currency`/`FinancialAccount.currency`, mai la valuta REALE gia'
    persistita in `asset_prices`) — il tasso JPY->EUR non veniva mai
    scaricato, lasciando la posizione bloccata sul fallback a costo storico
    anche dopo aver corretto l'etichettatura del prezzo."""
    from app.marketdata.base import FxQuote

    calls = []

    async def fake_fetch_fx_rate(self, from_currency, to_currency):
        calls.append((from_currency, to_currency))
        return FxQuote(rate=Decimal("0.0058"), as_of=date(2026, 8, 17))

    async def fake_fetch_fx_history(self, from_currency, to_currency, preset):
        return []  # storico non rilevante per questo test, vedi test dedicato al backfill

    async def fake_fetch_quote(self, asset):
        return None  # niente asset da aggiornare in questo test, solo la parte FX

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_rate", fake_fetch_fx_rate)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_history", fake_fetch_fx_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-fx-refresh-price-currency@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = me.json()["workspace_id"], me.json()["id"]
    # Asset dichiarato in EUR (come l'ha comprato l'utente), ma con un
    # prezzo gia' persistito in JPY (come lo quota davvero il provider).
    asset_id = await _create_asset(client, token, currency="EUR")
    await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-16", "price": "217.00", "currency": "JPY"},
        headers=_auth_headers(token),
    )

    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    await refresh_market_data_for_workspace(None, workspace_id, user_id)

    assert calls == [("JPY", "EUR")]


async def test_refresh_backfills_historical_fx_rates_for_a_new_pair(client, monkeypatch):
    """Regressione bug reale (segnalato dall'utente): il refresh scaricava
    da sempre SOLO il tasso di oggi. `fx_rate_expr`/`get_rate` cercano il
    tasso non piu' recente della data della riga da convertire — un solo
    tasso datato oggi non copre NESSUNA transazione passata, quindi dopo un
    cambio di `base_currency` le sezioni entrate/uscite risultavano
    completamente vuote, non solo parzialmente incomplete. Il refresh deve
    anche scaricare lo storico ("Max") la prima volta che vede una coppia."""
    from datetime import datetime, timezone

    from app.marketdata.base import FxQuote, PricePoint

    async def fake_fetch_fx_rate(self, from_currency, to_currency):
        return FxQuote(rate=Decimal("0.92"), as_of=date(2026, 8, 17))

    history_calls = []

    async def fake_fetch_fx_history(self, from_currency, to_currency, preset):
        history_calls.append((from_currency, to_currency, preset))
        return [
            PricePoint(at=datetime(2024, 1, 15, tzinfo=timezone.utc), price=Decimal("0.90")),
            PricePoint(at=datetime(2025, 6, 1, tzinfo=timezone.utc), price=Decimal("0.91")),
        ]

    async def fake_fetch_quote(self, asset):
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_rate", fake_fetch_fx_rate)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_history", fake_fetch_fx_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-fx-backfill@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = me.json()["workspace_id"], me.json()["id"]
    await _create_account(client, token, currency="USD")

    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    await refresh_market_data_for_workspace(None, workspace_id, user_id)

    assert history_calls == [("USD", "EUR", "Max")]

    from app.db.base import async_session_factory
    from app.services.fx_rate_service import get_rate

    async with async_session_factory() as db:
        # Una data storica lontana, mai coperta dal solo tasso "di oggi",
        # ora trova un tasso applicabile grazie al backfill.
        old_rate = await get_rate(db, "USD", "EUR", date(2024, 6, 1))
    assert old_rate == Decimal("0.90")


async def test_refresh_skips_history_backfill_when_pair_already_well_covered(client, monkeypatch):
    """Una coppia gia' storicizzata da tempo non deve rifare un fetch
    "Max" ad ogni singolo refresh — solo il tasso del giorno serve."""
    from app.marketdata.base import FxQuote
    from app.db.base import async_session_factory
    from app.services.fx_rate_service import upsert_rate

    async with async_session_factory() as db:
        await upsert_rate(db, "USD", "EUR", date(2020, 1, 1), Decimal("0.88"), "yahoo")
        await db.commit()

    history_calls = []

    async def fake_fetch_fx_rate(self, from_currency, to_currency):
        return FxQuote(rate=Decimal("0.92"), as_of=date(2026, 8, 17))

    async def fake_fetch_fx_history(self, from_currency, to_currency, preset):
        history_calls.append((from_currency, to_currency, preset))
        return []

    async def fake_fetch_quote(self, asset):
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_rate", fake_fetch_fx_rate)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_fx_history", fake_fetch_fx_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-fx-backfill-skip@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = me.json()["workspace_id"], me.json()["id"]
    await _create_account(client, token, currency="USD")

    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    await refresh_market_data_for_workspace(None, workspace_id, user_id)

    assert history_calls == []  # gia' coperta da anni: nessun fetch storico ripetuto


# --- Stato persistente del refresh (gap UX, non un toast effimero) --------


async def test_refresh_status_is_null_when_never_run(client):
    token = await _register(client, "md-refresh-status-null@example.com")
    response = await client.get("/api/v1/settings/market-data/refresh-status", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() is None


async def test_refresh_status_reflects_last_run_and_survives_a_page_reload(client):
    token = await _register(client, "md-refresh-status@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = me.json()["workspace_id"], me.json()["id"]

    # Simula il job del worker (nessun profilo attivo: nulla da scaricare,
    # ma lo stato dell'esecuzione va comunque registrato).
    await refresh_market_data_for_workspace(None, workspace_id, user_id)

    response = await client.get("/api/v1/settings/market-data/refresh-status", headers=_auth_headers(token))
    body = response.json()
    assert body["status"] == "success"
    assert body["finished_at"] is not None
    assert body["message"] is not None


async def test_refresh_does_not_enqueue_a_second_job_while_one_is_running(client, monkeypatch):
    import app.api.v1.settings_market_data as settings_market_data_module

    calls = []

    async def fake_enqueue(workspace_id, user_id):
        calls.append((workspace_id, user_id))
        return "fake-job-id"

    monkeypatch.setattr(settings_market_data_module, "enqueue_market_data_refresh", fake_enqueue)

    token = await _register(client, "md-refresh-no-double-enqueue@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = uuid.UUID(me.json()["workspace_id"]), uuid.UUID(me.json()["id"])

    await start_run(workspace_id, user_id, "market_data_refresh")

    response = await client.post("/api/v1/settings/market-data/refresh", headers=_auth_headers(token))
    assert response.status_code == 202
    assert calls == []  # un refresh e' gia' "running": nessun secondo job accodato


# --- Storico prezzi (Step 1 pagina dettaglio asset) ------------------------


async def test_price_history_invalid_preset_returns_400(client):
    token = await _register(client, "md-history-invalid-preset@example.com")
    asset_id = await _create_asset(client, token)
    response = await client.get(
        f"/api/v1/assets/{asset_id}/price-history?preset=2Y", headers=_auth_headers(token)
    )
    assert response.status_code == 400


async def test_price_history_without_active_profile_reports_no_history_support(client):
    token = await _register(client, "md-history-no-profile@example.com")
    asset_id = await _create_asset(client, token)
    response = await client.get(
        f"/api/v1/assets/{asset_id}/price-history?preset=1M", headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["supports_history"] is False
    assert body["points"] == []


async def test_price_history_daily_preset_persists_to_asset_prices(client, monkeypatch):
    from datetime import datetime, timezone

    from app.marketdata.base import PricePoint, Quote

    async def fake_fetch_history(self, asset, preset):
        return [
            PricePoint(at=datetime(2026, 8, 1, tzinfo=timezone.utc), price=Decimal("100.00")),
            PricePoint(at=datetime(2026, 8, 2, tzinfo=timezone.utc), price=Decimal("101.50")),
        ]

    # L'asset e' registrato in EUR ma il simbolo Yahoo risolto quota in USD
    # (caso reale: ISIN estero quotato in una valuta diversa da quella con
    # cui l'utente ha comprato) — la persistenza deve etichettare i prezzi
    # con la valuta REALE del provider, mai con `asset.currency` alla cieca
    # (bug reale corretto: prima sovrascriveva silenziosamente con EUR).
    async def fake_fetch_quote(self, asset):
        return Quote(price=Decimal("101.50"), currency="USD", as_of=date(2026, 8, 2))

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_history", fake_fetch_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-history-persist@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Yahoo", "provider": "yahoo"},
        headers=_auth_headers(token),
    )
    profiles = (
        await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    ).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    response = await client.get(
        f"/api/v1/assets/{asset_id}/price-history?preset=1M", headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["supports_history"] is True
    assert body["currency"] == "USD"
    assert len(body["points"]) == 2

    persisted = await client.get(f"/api/v1/assets/{asset_id}/prices", headers=_auth_headers(token))
    assert len(persisted.json()) == 2
    assert {p["source"] for p in persisted.json()} == {"yahoo"}
    assert {p["currency"] for p in persisted.json()} == {"USD"}


async def test_price_history_intraday_preset_is_not_persisted(client, monkeypatch):
    from datetime import datetime, timezone

    from app.marketdata.base import PricePoint

    async def fake_fetch_history(self, asset, preset):
        return [PricePoint(at=datetime(2026, 8, 17, 10, 30, tzinfo=timezone.utc), price=Decimal("100.00"))]

    async def fake_fetch_quote(self, asset):
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_history", fake_fetch_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-history-intraday@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Yahoo", "provider": "yahoo"},
        headers=_auth_headers(token),
    )
    profiles = (
        await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    ).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    response = await client.get(
        f"/api/v1/assets/{asset_id}/price-history?preset=1G", headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert len(response.json()["points"]) == 1

    persisted = await client.get(f"/api/v1/assets/{asset_id}/prices", headers=_auth_headers(token))
    assert persisted.json() == []


async def _seed_full_month_cache(client, token, asset_id, currency="EUR"):
    """Precarica direttamente `asset_prices` (bypassa il fetch live) con una
    riga per ogni giorno dell'ultimo mese, cosi' da coprire per intero la
    finestra attesa dal preset "1M" (vedi `_PRESET_LOOKBACK_DAYS`)."""
    from datetime import timedelta

    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.rls import rls_session
    from app.models.asset_price import AssetPrice as AssetPriceModel
    from app.models.user import User

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = uuid.UUID(me.json()["workspace_id"])
    email = me.json()["email"]

    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()

    today = date.today()
    async with rls_session(user.id) as db:
        for offset in range(0, 32):
            db.add(
                AssetPriceModel(
                    workspace_id=workspace_id,
                    asset_id=uuid.UUID(asset_id),
                    price_date=today - timedelta(days=offset),
                    price=Decimal("100.00"),
                    currency=currency,
                    source="yahoo",
                )
            )
        await db.commit()


async def test_price_history_serves_from_cache_within_ttl(client, monkeypatch):
    """Regressione: un cambio di range o una nuova apertura della pagina di
    dettaglio entro pochi minuti non deve ricontattare Yahoo se la cache
    locale copre gia' l'intera finestra richiesta ed e' stata aggiornata di
    recente — endpoint non ufficiale, noto per rispondere 429/999 anche
    senza aver davvero superato un limite dichiarato."""
    calls = []

    async def fake_fetch_history(self, asset, preset):
        calls.append("history")
        return []

    async def fake_fetch_quote(self, asset):
        calls.append("quote")
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_history", fake_fetch_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-history-cache-ttl@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )
    await _seed_full_month_cache(client, token, asset_id)

    response = await client.get(f"/api/v1/assets/{asset_id}/price-history?preset=1M", headers=_auth_headers(token))
    assert response.status_code == 200
    assert calls == []  # servito dalla cache, nessuna chiamata al provider
    assert len(response.json()["points"]) == 32
    assert response.json()["currency"] == "EUR"


async def test_price_history_refetches_live_after_cache_ttl_expires(client, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select, update

    from app.db.base import async_session_factory
    from app.db.rls import rls_session
    from app.marketdata.base import PricePoint
    from app.models.asset_price import AssetPrice as AssetPriceModel
    from app.models.user import User

    calls = []

    async def fake_fetch_history(self, asset, preset):
        calls.append("history")
        return [PricePoint(at=datetime.now(timezone.utc), price=Decimal("101.00"))]

    async def fake_fetch_quote(self, asset):
        calls.append("quote")
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_history", fake_fetch_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-history-cache-expired@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )
    await _seed_full_month_cache(client, token, asset_id)

    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.email == "md-history-cache-expired@example.com"))).scalar_one()
    async with rls_session(user.id) as db:
        await db.execute(
            update(AssetPriceModel).values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=20))
        )
        await db.commit()

    response = await client.get(f"/api/v1/assets/{asset_id}/price-history?preset=1M", headers=_auth_headers(token))
    assert response.status_code == 200
    assert "history" in calls  # cache scaduta (>15 minuti): ricontatta il provider


async def test_price_history_ignores_cache_when_range_not_fully_covered(client, monkeypatch):
    """Un solo giorno in cache non basta a coprire la finestra di un preset
    piu' ampio (es. "1A"): mai una cache PARZIALE, sarebbe un grafico con un
    "buco" iniziale piu' fuorviante di un fetch live."""
    calls = []

    async def fake_fetch_history(self, asset, preset):
        calls.append("history")
        return []

    async def fake_fetch_quote(self, asset):
        calls.append("quote")
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_history", fake_fetch_history)
    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_quote", fake_fetch_quote)

    token = await _register(client, "md-history-cache-partial@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )
    # Solo l'ultimo mese in cache: non basta per il preset "1A" (366 giorni).
    await _seed_full_month_cache(client, token, asset_id)

    response = await client.get(f"/api/v1/assets/{asset_id}/price-history?preset=1A", headers=_auth_headers(token))
    assert response.status_code == 200
    assert "history" in calls  # copertura insufficiente: mai servito dalla cache parziale


# --- Arricchimento asset (Step 3, best-effort) ------------------------------


async def test_asset_profile_without_active_profile_returns_all_none(client):
    token = await _register(client, "md-profile-no-provider@example.com")
    asset_id = await _create_asset(client, token)
    response = await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "issuer": None,
        "category": None,
        "aum": None,
        "distribution_policy": None,
        "display_name": None,
        "fetched_at": None,
    }


async def test_asset_display_name_appears_in_list_and_get_after_profile_cached(client, monkeypatch):
    """Regressione: il nome "pulito" dal provider (es. "Apple Inc.") deve
    comparire anche in GET /assets (lista, usata da Investimenti) e GET
    /assets/{id}, non solo nell'endpoint /profile dedicato — nessuna nuova
    chiamata al provider da li', solo lettura della cache gia' popolata
    visitando il dettaglio dell'asset."""
    from app.marketdata.base import AssetProfile

    async def fake_fetch_profile(self, asset):
        return AssetProfile(
            issuer=None, category=None, aum=None, distribution_policy=None,
            display_name="D-Wave Quantum Inc.",
        )

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_profile", fake_fetch_profile)

    token = await _register(client, "asset-display-name@example.com")
    # Nome grezzo come lo estrarrebbe il parser Trade Republic (con refuso
    # e suffisso di valore nominale tedesco).
    asset_id = await _create_asset(client, token, name="D-WAVE QUATUM DL-,0001", symbol="QBTS")

    # Prima di aver mai visitato il dettaglio: nessuna cache, display_name None.
    before = await client.get(f"/api/v1/assets/{asset_id}", headers=_auth_headers(token))
    assert before.json()["display_name"] is None
    assert before.json()["name"] == "D-WAVE QUATUM DL-,0001"  # il nome grezzo non e' mai toccato

    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )
    await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))

    after_get = await client.get(f"/api/v1/assets/{asset_id}", headers=_auth_headers(token))
    assert after_get.json()["display_name"] == "D-Wave Quantum Inc."
    assert after_get.json()["name"] == "D-WAVE QUATUM DL-,0001"  # invariato

    list_response = await client.get("/api/v1/assets", headers=_auth_headers(token))
    listed = next(a for a in list_response.json() if a["id"] == asset_id)
    assert listed["display_name"] == "D-Wave Quantum Inc."


async def test_asset_profile_fetches_and_caches(client, monkeypatch):
    from app.marketdata.base import AssetProfile

    calls = []

    async def fake_fetch_profile(self, asset):
        calls.append(asset.id)
        return AssetProfile(
            issuer="Vanguard",
            category="Global Equity",
            aum=Decimal("1000"),
            distribution_policy="accumulating",
            display_name="Vanguard FTSE All-World UCITS ETF (Acc)",
        )

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_profile", fake_fetch_profile)

    token = await _register(client, "md-profile-cache@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    first = await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert first.status_code == 200, first.text
    assert first.json()["issuer"] == "Vanguard"
    assert first.json()["display_name"] == "Vanguard FTSE All-World UCITS ETF (Acc)"
    assert first.json()["fetched_at"] is not None
    assert len(calls) == 1

    # Seconda chiamata entro la finestra di cache: nessun secondo fetch.
    second = await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert second.status_code == 200
    assert len(calls) == 1


async def test_asset_profile_keeps_stale_cache_when_refetch_fails(client, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.marketdata.base import AssetProfile

    async def fake_fetch_profile_ok(self, asset):
        return AssetProfile(issuer="Vanguard", category=None, aum=None, distribution_policy=None)

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_profile", fake_fetch_profile_ok)

    token = await _register(client, "md-profile-stale@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )
    await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))

    # Forza la cache a risultare scaduta, poi simula un fetch fallito
    # (provider che ritorna None): la riga esistente non deve sparire.
    from sqlalchemy import select, update

    from app.db.base import async_session_factory
    from app.db.rls import rls_session
    from app.models.asset_profile import AssetProfile as AssetProfileModel
    from app.models.user import User

    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.email == "md-profile-stale@example.com"))).scalar_one()
    async with rls_session(user.id) as db:
        await db.execute(
            update(AssetProfileModel).values(fetched_at=datetime.now(timezone.utc) - timedelta(days=31))
        )
        await db.commit()

    async def fake_fetch_profile_fail(self, asset):
        return None

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_profile", fake_fetch_profile_fail)

    response = await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["issuer"] == "Vanguard"  # cache scaduta ma mantenuta, non azzerata


async def test_refresh_enqueues_again_after_a_previous_run_completed(client, monkeypatch):
    """Regressione del bug reale trovato testando dal vivo: l'id fisso per
    workspace che arq usava per il dedup bloccava silenziosamente ANCHE i
    click successivi al primo refresh completato (il risultato resta in
    Redis per un'ora) — un'esecuzione GIA' TERMINATA non deve mai impedire
    il trigger successivo."""
    import app.api.v1.settings_market_data as settings_market_data_module

    calls = []

    async def fake_enqueue(workspace_id, user_id):
        calls.append((workspace_id, user_id))
        return "fake-job-id"

    monkeypatch.setattr(settings_market_data_module, "enqueue_market_data_refresh", fake_enqueue)

    token = await _register(client, "md-refresh-reenqueue@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id, user_id = uuid.UUID(me.json()["workspace_id"]), uuid.UUID(me.json()["id"])

    await start_run(workspace_id, user_id, "market_data_refresh")
    await finish_run(workspace_id, user_id, "market_data_refresh", success=True, message="ok")

    response = await client.post("/api/v1/settings/market-data/refresh", headers=_auth_headers(token))
    assert response.status_code == 202
    assert len(calls) == 1


async def test_asset_profile_retries_when_display_name_missing_despite_fresh_cache(client, monkeypatch):
    """Regressione bug reale (D-Wave): un fetch riuscito ma con
    `display_name=None` (endpoint Yahoo noto per essere fragile) non deve
    bloccare per 30 giorni ogni tentativo successivo — a differenza degli
    altri campi (issuer/category/aum), un nome mancante non e' mai
    considerato "cache fresca", quindi la pagina successiva ritenta subito."""
    from app.marketdata.base import AssetProfile

    calls = []

    async def fake_fetch_profile_no_name(self, asset):
        calls.append(asset.id)
        return AssetProfile(issuer="Vanguard", category=None, aum=None, distribution_policy=None, display_name=None)

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_profile", fake_fetch_profile_no_name)

    token = await _register(client, "md-profile-missing-name@example.com")
    asset_id = await _create_asset(client, token)
    await client.post(
        "/api/v1/settings/market-data/profiles", json={"name": "Yahoo", "provider": "yahoo"}, headers=_auth_headers(token)
    )
    profiles = (await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))).json()
    await client.post(
        f"/api/v1/settings/market-data/profiles/{profiles[0]['id']}/activate", headers=_auth_headers(token)
    )

    first = await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert first.json()["display_name"] is None
    assert len(calls) == 1

    # Cache "fresca" per fetched_at, ma senza nome: deve ritentare subito,
    # non aspettare 30 giorni come per gli altri campi.
    second = await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert len(calls) == 2
    # L'issuer gia' noto non deve sparire nel frattempo (merge, non overwrite cieco).
    assert second.json()["issuer"] == "Vanguard"

    async def fake_fetch_profile_with_name(self, asset):
        calls.append(asset.id)
        return AssetProfile(issuer=None, category=None, aum=None, distribution_policy=None, display_name="D-Wave Quantum Inc.")

    monkeypatch.setattr("app.marketdata.providers.yahoo.YahooProvider.fetch_profile", fake_fetch_profile_with_name)

    third = await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert len(calls) == 3
    assert third.json()["display_name"] == "D-Wave Quantum Inc."
    # Il nuovo fetch non porta issuer (None): il valore gia' noto resta.
    assert third.json()["issuer"] == "Vanguard"

    # Adesso che il nome c'e', la cache torna a essere considerata fresca.
    # La chiamata serve per il suo effetto (non deve incrementare `calls`),
    # la risposta non viene ispezionata.
    await client.get(f"/api/v1/assets/{asset_id}/profile", headers=_auth_headers(token))
    assert len(calls) == 3

"""Factory che risolve il provider concreto da un profilo `MarketDataProfile`
(SPEC §38). Stesso ruolo di `app/ai/registry.py:build_classifier` — unico
punto che conosce l'elenco dei provider disponibili.

La API key viene decifrata solo qui, al momento dell'uso, mai altrove
(schemas/API restituiscono sempre `api_key_set`, mai il valore).
"""
from app.core.crypto import decrypt_secret
from app.marketdata.base import MarketDataProvider
from app.marketdata.providers.custom import CustomProvider
from app.marketdata.providers.manual import ManualMarketDataProvider
from app.marketdata.providers.none import NoMarketDataProvider
from app.marketdata.providers.stooq import StooqProvider
from app.marketdata.providers.yahoo import YahooProvider
from app.models.market_data_profile import MarketDataProfile


def build_provider(profile: MarketDataProfile | None) -> MarketDataProvider:
    """`profile=None` significa "nessun profilo attivo per questo
    workspace" (SPEC §38, market data disabilitato) — non un errore, ritorna
    semplicemente `NoMarketDataProvider`. Le posizioni restano valorizzate a
    costo storico (vedi `app/services/portfolio_analytics.py`)."""
    if profile is None:
        return NoMarketDataProvider()

    if profile.provider == "manual":
        return ManualMarketDataProvider()
    if profile.provider == "stooq":
        return StooqProvider()
    if profile.provider == "yahoo":
        return YahooProvider()
    if profile.provider == "custom":
        api_key = decrypt_secret(profile.api_key_encrypted) if profile.api_key_encrypted else None
        return CustomProvider(
            endpoint=profile.endpoint or "",
            api_key=api_key,
            price_field=profile.price_field or "price",
            currency_field=profile.currency_field,
        )

    return NoMarketDataProvider()

"""Test unitari della parte pura dei provider market data (milestone 09b) —
nessuna dipendenza di rete, come `test_position_calc.py` per il dominio
Portfolio. Le chiamate HTTP vere (stooq/yahoo/custom) non sono mockate qui,
stessa scelta gia' fatta per i provider AI (nessun test unitario su
ollama.py/openai.py in questo repo): il valore sta nel testare la logica
propria di Lumio, non il comportamento di un servizio terzo.
"""
import uuid

import pytest

from app.marketdata.base import AssetRef, MarketDataProviderError
from app.marketdata.providers.custom import CustomProvider, _resolve_path
from app.marketdata.providers.manual import ManualMarketDataProvider
from app.marketdata.providers.none import NoMarketDataProvider


def _asset(**overrides) -> AssetRef:
    defaults = dict(id=uuid.uuid4(), symbol="VWCE", isin=None, name="Vanguard FTSE All-World", currency="EUR")
    defaults.update(overrides)
    return AssetRef(**defaults)


def test_resolve_path_flat_key():
    assert _resolve_path({"price": 123.45}, "price") == 123.45


def test_resolve_path_nested_dict():
    assert _resolve_path({"quote": {"price": 42}}, "quote.price") == 42


def test_resolve_path_through_list_index():
    assert _resolve_path({"data": [{"price": 7}]}, "data.0.price") == 7


def test_resolve_path_missing_key_returns_none():
    assert _resolve_path({"quote": {}}, "quote.price") is None


def test_resolve_path_invalid_list_index_returns_none():
    assert _resolve_path({"data": [1, 2]}, "data.9") is None


async def test_no_provider_never_raises_and_returns_none():
    provider = NoMarketDataProvider()
    assert await provider.fetch_quote(_asset()) is None
    await provider.test_connection()  # non deve mai lanciare


async def test_manual_provider_never_fetches_automatically():
    # SPEC §38 "dati manuali": nessun fetch, l'inserimento vero avviene via
    # PUT /assets/{id}/prices, non da questa classe.
    provider = ManualMarketDataProvider()
    assert await provider.fetch_quote(_asset()) is None
    await provider.test_connection()


async def test_custom_provider_without_endpoint_raises_configuration_error():
    provider = CustomProvider(endpoint="", api_key=None, price_field="price", currency_field=None)
    with pytest.raises(MarketDataProviderError, match="Endpoint non configurato"):
        await provider.test_connection()


async def test_custom_provider_without_symbol_returns_none_without_network_call():
    provider = CustomProvider(
        endpoint="https://example.invalid/{symbol}", api_key=None, price_field="price", currency_field=None
    )
    assert await provider.fetch_quote(_asset(symbol=None)) is None

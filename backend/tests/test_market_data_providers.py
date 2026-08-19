"""Test unitari della parte pura dei provider market data (milestone 09b) —
nessuna dipendenza di rete, come `test_position_calc.py` per il dominio
Portfolio. Le chiamate HTTP vere (stooq/yahoo/custom) non sono mockate qui,
stessa scelta gia' fatta per i provider AI (nessun test unitario su
ollama.py/openai.py in questo repo): il valore sta nel testare la logica
propria di Lumio, non il comportamento di un servizio terzo.
"""
import uuid
from decimal import Decimal

import pytest

from app.marketdata.base import AssetRef, MarketDataProviderError
from app.marketdata.providers.custom import CustomProvider, _resolve_path
from app.marketdata.providers.manual import ManualMarketDataProvider
from app.marketdata.providers.none import NoMarketDataProvider
from app.marketdata.providers.stooq import StooqProvider
from app.marketdata.providers.yahoo import YahooProvider, _infer_distribution_policy


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


async def test_none_and_manual_and_stooq_and_custom_declare_no_history_support():
    # `fetch_history` -> None e' il modo con cui un provider dichiara "non
    # supporto lo storico" (mai un'eccezione, mai una lista vuota che si
    # confonderebbe con "nessun dato in questo range").
    assert await NoMarketDataProvider().fetch_history(_asset(), "1M") is None
    assert await ManualMarketDataProvider().fetch_history(_asset(), "1M") is None
    assert await StooqProvider().fetch_history(_asset(), "1M") is None
    assert (
        await CustomProvider(
            endpoint="https://example.invalid/{symbol}", api_key=None, price_field="price", currency_field=None
        ).fetch_history(_asset(), "1M")
        is None
    )


# --- YahooProvider.fetch_history ------------------------------------------


def _yahoo_chart_body(timestamps: list[int], closes: list[float | None]) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "EUR"},
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ],
            "error": None,
        }
    }


async def test_yahoo_fetch_history_unknown_preset_returns_none():
    provider = YahooProvider()
    assert await provider.fetch_history(_asset(), "2Y") is None


async def test_yahoo_fetch_history_without_symbol_or_isin_returns_none():
    provider = YahooProvider()
    assert await provider.fetch_history(_asset(symbol=None, isin=None), "1M") is None


async def test_yahoo_fetch_history_skips_null_closes(httpx_mock):
    httpx_mock.add_response(
        url="https://query1.finance.yahoo.com/v8/finance/chart/VWCE?range=1mo&interval=1d",
        json=_yahoo_chart_body(
            timestamps=[1735689600, 1735776000, 1735862400],
            closes=[101.5, None, 103.25],
        ),
    )
    provider = YahooProvider()
    points = await provider.fetch_history(_asset(), "1M")
    assert points is not None
    assert len(points) == 2
    assert points[0].price == Decimal("101.5")
    assert points[1].price == Decimal("103.25")


async def test_yahoo_fetch_history_empty_result_returns_empty_list(httpx_mock):
    httpx_mock.add_response(
        url="https://query1.finance.yahoo.com/v8/finance/chart/VWCE?range=1mo&interval=1d",
        json={"chart": {"result": [], "error": {"code": "Not Found"}}},
    )
    provider = YahooProvider()
    assert await provider.fetch_history(_asset(), "1M") == []


# --- _infer_distribution_policy (euristica sul nome del fondo) -------------


def test_infer_distribution_policy_accumulating():
    assert _infer_distribution_policy("Vanguard FTSE All-World UCITS ETF (Acc)") == "accumulating"


def test_infer_distribution_policy_distributing():
    assert _infer_distribution_policy("iShares Core MSCI World UCITS ETF Dist") == "distributing"


def test_infer_distribution_policy_no_match_returns_none():
    assert _infer_distribution_policy("Apple Inc") is None


def test_infer_distribution_policy_does_not_false_positive_on_substring():
    # "Accenture" contiene "acc" come sottostringa ma non e' un fondo ad
    # accumulazione — l'euristica cerca "Acc" come parola intera.
    assert _infer_distribution_policy("Accenture Investment Trust") is None


def test_infer_distribution_policy_none_name_returns_none():
    assert _infer_distribution_policy(None) is None


# --- YahooProvider.fetch_profile (best-effort, mai un'eccezione) -----------


def _crumb_and_cookie_mocks(httpx_mock):
    httpx_mock.add_response(url="https://fc.yahoo.com", text="")
    httpx_mock.add_response(url="https://query1.finance.yahoo.com/v1/test/getcrumb", text="abc123")


async def test_yahoo_fetch_profile_without_symbol_or_isin_returns_none():
    provider = YahooProvider()
    assert await provider.fetch_profile(_asset(symbol=None, isin=None)) is None


async def test_yahoo_fetch_profile_parses_fund_fields(httpx_mock):
    _crumb_and_cookie_mocks(httpx_mock)
    httpx_mock.add_response(
        url="https://query2.finance.yahoo.com/v10/finance/quoteSummary/VWCE?modules=quoteType%2CfundProfile%2CsummaryDetail&crumb=abc123",
        json={
            "quoteSummary": {
                "result": [
                    {
                        "quoteType": {"longName": "Vanguard FTSE All-World UCITS ETF (Acc)"},
                        "fundProfile": {"family": "Vanguard", "categoryName": "Global Equity"},
                        "summaryDetail": {"totalAssets": {"raw": 15000000000, "fmt": "15B"}},
                    }
                ]
            }
        },
    )
    provider = YahooProvider()
    result = await provider.fetch_profile(_asset())
    assert result is not None
    assert result.issuer == "Vanguard"
    assert result.category == "Global Equity"
    assert result.aum == Decimal("15000000000")
    assert result.distribution_policy == "accumulating"
    assert result.display_name == "Vanguard FTSE All-World UCITS ETF (Acc)"


async def test_yahoo_fetch_profile_leaves_issuer_none_for_a_stock_without_fund_profile(httpx_mock):
    # Regressione: `summaryProfile.industry` (es. "Consumer Electronics" per
    # Apple) NON e' un emittente — un'azione senza `fundProfile` deve
    # risultare in `issuer=None`, mai in un valore fuorviante.
    _crumb_and_cookie_mocks(httpx_mock)
    httpx_mock.add_response(
        url="https://query2.finance.yahoo.com/v10/finance/quoteSummary/VWCE?modules=quoteType%2CfundProfile%2CsummaryDetail&crumb=abc123",
        json={
            "quoteSummary": {
                "result": [
                    {
                        "quoteType": {"longName": "Apple Inc"},
                        "summaryProfile": {"industry": "Consumer Electronics"},
                        "summaryDetail": {},
                    }
                ]
            }
        },
    )
    provider = YahooProvider()
    result = await provider.fetch_profile(_asset())
    assert result is not None
    assert result.issuer is None
    # Il nome pulito e' comunque disponibile (nessuna dipendenza da
    # fundProfile) — utile per un'azione il cui nome grezzo dal parser
    # Trade Republic porta suffissi di borsa tedeschi o refusi del broker.
    assert result.display_name == "Apple Inc"


async def test_yahoo_fetch_profile_returns_none_on_crumb_failure(httpx_mock):
    httpx_mock.add_response(url="https://fc.yahoo.com", text="")
    httpx_mock.add_response(url="https://query1.finance.yahoo.com/v1/test/getcrumb", status_code=401)
    provider = YahooProvider()
    assert await provider.fetch_profile(_asset()) is None


async def test_yahoo_fetch_profile_returns_none_on_empty_result(httpx_mock):
    _crumb_and_cookie_mocks(httpx_mock)
    httpx_mock.add_response(
        url="https://query2.finance.yahoo.com/v10/finance/quoteSummary/VWCE?modules=quoteType%2CfundProfile%2CsummaryDetail&crumb=abc123",
        json={"quoteSummary": {"result": [], "error": {"code": "Not Found"}}},
    )
    provider = YahooProvider()
    assert await provider.fetch_profile(_asset()) is None


async def test_none_manual_stooq_custom_declare_no_profile_support():
    assert await NoMarketDataProvider().fetch_profile(_asset()) is None
    assert await ManualMarketDataProvider().fetch_profile(_asset()) is None
    assert await StooqProvider().fetch_profile(_asset()) is None
    assert (
        await CustomProvider(
            endpoint="https://example.invalid/{symbol}", api_key=None, price_field="price", currency_field=None
        ).fetch_profile(_asset())
        is None
    )


# --- YahooProvider.fetch_fx_rate / fetch_fx_history (sistema di valute) ----


async def test_yahoo_fetch_fx_rate_parses_chart_response(httpx_mock):
    httpx_mock.add_response(
        url="https://query1.finance.yahoo.com/v8/finance/chart/USDEUR=X",
        json={
            "chart": {
                "result": [
                    {"meta": {"regularMarketPrice": 0.92, "regularMarketTime": 1735689600}},
                ],
                "error": None,
            }
        },
    )
    provider = YahooProvider()
    quote = await provider.fetch_fx_rate("USD", "EUR")
    assert quote is not None
    assert quote.rate == Decimal("0.92")


async def test_yahoo_fetch_fx_rate_returns_none_on_empty_result(httpx_mock):
    httpx_mock.add_response(
        url="https://query1.finance.yahoo.com/v8/finance/chart/XYZABC=X",
        json={"chart": {"result": [], "error": {"code": "Not Found"}}},
    )
    provider = YahooProvider()
    assert await provider.fetch_fx_rate("XYZ", "ABC") is None


async def test_yahoo_fetch_fx_history_skips_null_closes(httpx_mock):
    httpx_mock.add_response(
        url="https://query1.finance.yahoo.com/v8/finance/chart/USDEUR=X?range=1mo&interval=1d",
        json={
            "chart": {
                "result": [
                    {
                        "timestamp": [1735689600, 1735776000, 1735862400],
                        "indicators": {"quote": [{"close": [0.91, None, 0.93]}]},
                    }
                ],
                "error": None,
            }
        },
    )
    provider = YahooProvider()
    points = await provider.fetch_fx_history("USD", "EUR", "1M")
    assert points is not None
    assert len(points) == 2
    assert points[0].price == Decimal("0.91")
    assert points[1].price == Decimal("0.93")


async def test_yahoo_fetch_fx_history_unknown_preset_returns_none():
    provider = YahooProvider()
    assert await provider.fetch_fx_history("USD", "EUR", "2Y") is None


async def test_none_manual_stooq_custom_declare_no_fx_support():
    assert await NoMarketDataProvider().fetch_fx_rate("USD", "EUR") is None
    assert await NoMarketDataProvider().fetch_fx_history("USD", "EUR", "1M") is None
    assert await ManualMarketDataProvider().fetch_fx_rate("USD", "EUR") is None
    assert await StooqProvider().fetch_fx_rate("USD", "EUR") is None
    assert (
        await CustomProvider(
            endpoint="https://example.invalid/{symbol}", api_key=None, price_field="price", currency_field=None
        ).fetch_fx_rate("USD", "EUR")
        is None
    )

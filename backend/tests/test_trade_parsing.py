"""Test unitari del parsing automatico dei movimenti Trade Republic
(milestone 09c) — nessuna dipendenza da DB/FastAPI, come
`test_position_calc.py`. Il formato testato e' quello verificato sui dati
reali dell'utente durante lo sviluppo (48/48 righe, vedi docstring di
`trade_parsing.py`); qui si usano ISIN/nomi di fantasia, mai i dati reali.
"""
from decimal import Decimal

from app.services.trade_parsing import parse_trade_description


def test_savings_plan_execution_parses_as_buy_with_fractional_quantity():
    trade = parse_trade_description(
        "Savings plan execution IE00B4L5Y983 iShares III plc - iShares Core MSCI World UCITS ETF USD (Acc), "
        "quantity: 1.272657"
    )
    assert trade is not None
    assert trade.type == "buy"
    assert trade.isin == "IE00B4L5Y983"
    assert trade.asset_name == "iShares III plc - iShares Core MSCI World UCITS ETF USD (Acc)"
    assert trade.quantity == Decimal("1.272657")
    assert trade.source_type_raw == "Savings plan execution"


def test_buy_trade_parses_as_buy_with_integer_quantity():
    trade = parse_trade_description("Buy trade US0378331005 APPLE INC, quantity: 10")
    assert trade is not None
    assert trade.type == "buy"
    assert trade.isin == "US0378331005"
    assert trade.asset_name == "APPLE INC"
    assert trade.quantity == Decimal("10")


def test_sell_trade_parses_as_sell():
    trade = parse_trade_description("Sell trade US0378331005 APPLE INC, quantity: 4")
    assert trade is not None
    assert trade.type == "sell"


def test_unrecognized_format_returns_none_without_raising():
    assert parse_trade_description("Qualcosa di completamente diverso") is None


def test_missing_comma_before_quantity_does_not_match():
    # Formato osservato SOLO con la virgola prima di "quantity:" — un
    # formato leggermente diverso (es. un fixture di test piu' vecchio,
    # M05) non deve produrre un match falso positivo.
    assert parse_trade_description("Savings plan execution TEST1234567 quantity: 5") is None


def test_invalid_isin_shape_does_not_match():
    assert parse_trade_description("Buy trade NOTANISIN NOME ASSET, quantity: 1") is None


def test_zero_quantity_returns_none():
    assert parse_trade_description("Buy trade US0378331005 APPLE INC, quantity: 0") is None

"""Test unitari del rilevamento di operazioni societarie — nessun DB. I dati sono
SINTETICI (societa' e numeri inventati): riproducono solo la struttura di un
raggruppamento 10.000:1 con cambio di ISIN (acquisti sul vecchio titolo,
vendita sul nuovo)."""
from datetime import date
from decimal import Decimal

from app.services.corporate_action_calc import (
    AssetActivity,
    detect_split_suggestions,
    is_derivative_name,
    suggest_split_date,
)


def _old_asset(**overrides) -> AssetActivity:
    base = dict(
        asset_id="old",
        name="ACME SE NOM. EO 1",
        currency="EUR",
        net_quantity=Decimal("200000"),
        first_date=date(2024, 1, 14),
        last_date=date(2024, 3, 3),
        first_price=Decimal("0.0025"),
        last_price=Decimal("0.0045"),
    )
    base.update(overrides)
    return AssetActivity(**base)


def _new_asset(**overrides) -> AssetActivity:
    base = dict(
        asset_id="new",
        name="ACME SE NOM.EO 1",
        currency="EUR",
        net_quantity=Decimal("-20"),
        first_date=date(2024, 4, 8),
        last_date=date(2024, 4, 8),
        first_price=Decimal("34.90"),
        last_price=Decimal("34.90"),
    )
    base.update(overrides)
    return AssetActivity(**base)


def test_detects_reverse_split_from_quantities():
    result = detect_split_suggestions([_old_asset(), _new_asset()])
    assert len(result) == 1
    suggestion = result[0]
    assert (suggestion.source_asset_id, suggestion.target_asset_id) == ("old", "new")
    assert suggestion.ratio == Decimal("0.0001")
    assert suggestion.confidence == "high"
    assert suggestion.quantity_matched is True
    assert suggestion.split_date == date(2024, 4, 7)


def test_detects_price_jump_without_sale_as_medium_confidence():
    new_asset = _new_asset(net_quantity=Decimal("20"), first_price=Decimal("40"))
    result = detect_split_suggestions([_old_asset(), new_asset])
    assert len(result) == 1
    assert result[0].confidence == "medium"
    assert result[0].quantity_matched is False
    assert result[0].ratio == Decimal("0.0001")


def test_ignores_unrelated_assets_with_different_names():
    other = _new_asset(name="QUANTUM WIDGETS CORP.")
    assert detect_split_suggestions([_old_asset(), other]) == []


def test_non_standard_quantity_ratio_never_yields_high_confidence():
    result = detect_split_suggestions([_old_asset(), _new_asset(net_quantity=Decimal("-17"))])
    assert [s.confidence for s in result] == ["medium"]
    assert result[0].quantity_matched is False


def test_ignores_pair_when_price_is_inconsistent_with_the_ratio():
    # Quantita' coerenti con 10.000:1 ma prezzo invariato: non e' uno split.
    assert detect_split_suggestions([_old_asset(), _new_asset(first_price=Decimal("0.005"))]) == []


def test_ignores_different_currencies_and_earlier_target():
    assert detect_split_suggestions([_old_asset(), _new_asset(currency="USD")]) == []
    assert detect_split_suggestions([_old_asset(), _new_asset(first_date=date(2024, 2, 1))]) == []


def test_closed_source_position_is_never_suggested():
    assert detect_split_suggestions([_old_asset(net_quantity=Decimal("0")), _new_asset()]) == []


def test_suggest_split_date_never_precedes_last_source_movement():
    assert suggest_split_date(date(2024, 3, 3), date(2024, 4, 8)) == date(2024, 4, 7)
    assert suggest_split_date(date(2024, 4, 8), date(2024, 4, 8)) == date(2024, 4, 8)


def test_is_derivative_name():
    assert is_derivative_name("Turbo auf EXAMPLE CORP. DL-,10")
    assert is_derivative_name("Mini Future Long INDEX")
    assert is_derivative_name("KNOCK-OUT Call Foobar")
    assert not is_derivative_name("iShares Core MSCI World UCITS ETF")
    assert not is_derivative_name("Acme Group")

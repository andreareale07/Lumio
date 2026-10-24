"""Test unitari del rilevamento di operazioni societarie — nessun DB. I numeri
del caso Acme sono quelli reali dell'utente (acquisti 200.000 azioni a
0,0022/0,0049, vendita di 20 a 35,52 dopo un raggruppamento 10.000:1)."""
from datetime import date
from decimal import Decimal

from app.services.corporate_action_calc import (
    AssetActivity,
    detect_split_suggestions,
    is_derivative_name,
    suggest_split_date,
)


def _atos_old(**overrides) -> AssetActivity:
    base = dict(
        asset_id="old",
        name="ACME SE NOM. EO 1",
        currency="EUR",
        net_quantity=Decimal("200000"),
        first_date=date(2025, 1, 23),
        last_date=date(2025, 3, 6),
        first_price=Decimal("0.0025"),
        last_price=Decimal("0.0045"),
    )
    base.update(overrides)
    return AssetActivity(**base)


def _atos_new(**overrides) -> AssetActivity:
    base = dict(
        asset_id="new",
        name="ACME SE NOM.EO 1",
        currency="EUR",
        net_quantity=Decimal("-20"),
        first_date=date(2025, 4, 28),
        last_date=date(2025, 4, 28),
        first_price=Decimal("34.90"),
        last_price=Decimal("34.90"),
    )
    base.update(overrides)
    return AssetActivity(**base)


def test_detects_atos_reverse_split_from_quantities():
    result = detect_split_suggestions([_atos_old(), _atos_new()])
    assert len(result) == 1
    suggestion = result[0]
    assert (suggestion.source_asset_id, suggestion.target_asset_id) == ("old", "new")
    assert suggestion.ratio == Decimal("0.0001")
    assert suggestion.confidence == "high"
    assert suggestion.quantity_matched is True
    assert suggestion.split_date == date(2025, 4, 27)


def test_detects_price_jump_without_sale_as_medium_confidence():
    new_asset = _atos_new(net_quantity=Decimal("20"), first_price=Decimal("40"))
    result = detect_split_suggestions([_atos_old(), new_asset])
    assert len(result) == 1
    assert result[0].confidence == "medium"
    assert result[0].quantity_matched is False
    assert result[0].ratio == Decimal("0.0001")


def test_ignores_unrelated_assets_with_different_names():
    other = _atos_new(name="QUANTUM EMOTION CORP.")
    assert detect_split_suggestions([_atos_old(), other]) == []


def test_non_standard_quantity_ratio_never_yields_high_confidence():
    result = detect_split_suggestions([_atos_old(), _atos_new(net_quantity=Decimal("-17"))])
    assert [s.confidence for s in result] == ["medium"]
    assert result[0].quantity_matched is False


def test_ignores_pair_when_price_is_inconsistent_with_the_ratio():
    # Quantita' coerenti con 10.000:1 ma prezzo invariato: non e' uno split.
    assert detect_split_suggestions([_atos_old(), _atos_new(first_price=Decimal("0.005"))]) == []


def test_ignores_different_currencies_and_earlier_target():
    assert detect_split_suggestions([_atos_old(), _atos_new(currency="USD")]) == []
    assert detect_split_suggestions([_atos_old(), _atos_new(first_date=date(2025, 2, 1))]) == []


def test_closed_source_position_is_never_suggested():
    assert detect_split_suggestions([_atos_old(net_quantity=Decimal("0")), _atos_new()]) == []


def test_suggest_split_date_never_precedes_last_source_movement():
    assert suggest_split_date(date(2025, 3, 6), date(2025, 4, 28)) == date(2025, 4, 27)
    assert suggest_split_date(date(2025, 4, 28), date(2025, 4, 28)) == date(2025, 4, 28)


def test_is_derivative_name():
    assert is_derivative_name("Turbo auf EXAMPLE CORP. DL-,10")
    assert is_derivative_name("Mini Future Long DAX")
    assert is_derivative_name("KNOCK-OUT Call Example")
    assert not is_derivative_name("iShares Core MSCI World UCITS ETF")
    assert not is_derivative_name("Acme Group")

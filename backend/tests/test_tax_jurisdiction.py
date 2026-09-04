"""Invarianti su `ItalyTaxJurisdiction` (SPEC_TAX_REGIME.md FETTA 1) —
nessun DB."""
from datetime import date
from decimal import Decimal

import pytest

from app.tax.base import AssetTaxRef, TaxRulesetNotFound
from app.tax.jurisdictions.italy import ItalyTaxJurisdiction

jur = ItalyTaxJurisdiction()


def test_ruleset_at_switches_exactly_on_2014_07_01():
    assert jur.ruleset_at(date(2014, 6, 30)).code == "IT-2012-01"
    assert jur.ruleset_at(date(2014, 7, 1)).code == "IT-2014-07"


def test_ruleset_at_before_first_ruleset_raises():
    with pytest.raises(TaxRulesetNotFound):
        jur.ruleset_at(date(1999, 12, 31))


def test_usable_loss_applies_4808_before_2012():
    result = jur.usable_loss(Decimal("1000"), formation_date=date(2011, 6, 1), on=date(2015, 1, 1))
    assert result.coefficient == Decimal("0.4808")
    assert result.usable_amount == Decimal("480.80")
    assert result.conversion_reference is not None


def test_usable_loss_applies_7692_between_2012_and_mid_2014():
    result = jur.usable_loss(Decimal("1000"), formation_date=date(2013, 1, 1), on=date(2015, 1, 1))
    assert result.coefficient == Decimal("0.7692")
    assert result.usable_amount == Decimal("769.20")


def test_usable_loss_no_conversion_when_consumed_before_2014_07_01():
    # Minusvalenza 2013 usata a marzo 2014 (prima del 1/7): il ruleset
    # consumante e' ancora IT-2012-01, che non ha LossConversion.
    result = jur.usable_loss(Decimal("1000"), formation_date=date(2013, 1, 1), on=date(2014, 3, 1))
    assert result.coefficient == Decimal("1")
    assert result.usable_amount == Decimal("1000.00")
    assert result.conversion_reference is None


def test_usable_loss_no_conversion_for_losses_formed_after_mid_2014():
    result = jur.usable_loss(Decimal("1000"), formation_date=date(2015, 1, 1), on=date(2016, 1, 1))
    assert result.coefficient == Decimal("1")
    assert result.conversion_reference is None


def test_harmonized_etf_asymmetry_gain_vs_loss_category():
    on = date(2020, 1, 1)
    treatment = jur.treatment("etf_armonizzato", "sale", on)
    assert treatment.gain_category == "redditi_capitale"
    assert treatment.loss_category == "redditi_diversi"


def test_can_offset_denies_diversi_against_capitale():
    on = date(2020, 1, 1)
    assert jur.can_offset("redditi_diversi", "redditi_capitale", on) is False


def test_can_offset_allows_diversi_against_diversi_symmetrically():
    on = date(2020, 1, 1)
    assert jur.can_offset("redditi_diversi", "redditi_diversi", on) is True


def test_derive_asset_class_etf_without_strong_signal_is_unclassified():
    # asset_type="etf" da solo (es. un ETC su oro fisico rilevato dalla
    # regex di hint) non basta senza ISIN UE + "UCITS" nel nome — trappola
    # nota (SPEC_TAX_REGIME.md, test_tax_classification.py equivalente).
    ref = AssetTaxRef(asset_type="etf", isin="DE000A0S9GB0", name="Xetra-Gold")
    assert jur.derive_asset_class(ref, date(2020, 1, 1)) == "unclassified"


def test_derive_asset_class_harmonized_etf_with_strong_signal():
    ref = AssetTaxRef(asset_type="etf", isin="IE00B4L5Y983", name="iShares Core MSCI World UCITS ETF")
    assert jur.derive_asset_class(ref, date(2020, 1, 1)) == "etf_armonizzato"


def test_derive_asset_class_crypto_is_not_codified():
    ref = AssetTaxRef(asset_type="crypto", isin=None, name="Bitcoin")
    asset_class = jur.derive_asset_class(ref, date(2020, 1, 1))
    classes_by_code = {c.code: c for c in jur.tax_asset_classes(date(2020, 1, 1))}
    assert classes_by_code[asset_class].codified is False

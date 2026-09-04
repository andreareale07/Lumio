"""`build_loss_pocket` (SPEC_TAX_REGIME.md FETTA 1) — puro, nessun DB."""
from datetime import date
from decimal import Decimal

from app.services.tax_calc import LossPocketEntry, build_loss_pocket
from app.tax.rulesets.italy import IT_RULESETS

_RULESET_2024 = next(r for r in IT_RULESETS if r.code == "IT-2014-07")


def _entry(formation_date, nominal, perimeter="dichiarativo", ruleset_code="IT-2014-07"):
    return LossPocketEntry(
        formation_date=formation_date,
        nominal=Decimal(nominal),
        income_category="redditi_diversi",
        perimeter=perimeter,
        source="user_opening",
        formed_under_ruleset_code=ruleset_code,
    )


def test_rows_are_ordered_fifo_by_formation_date_per_perimeter():
    entries = [_entry(date(2022, 1, 1), "500"), _entry(date(2020, 1, 1), "300")]
    result = build_loss_pocket(entries, _RULESET_2024, on=date(2023, 1, 1))
    assert [r.formation_date for r in result.rows] == [date(2020, 1, 1), date(2022, 1, 1)]


def test_expired_entry_excluded_from_total_but_present_in_detail():
    # Formata nel 2018: scade 31/12/2022 (4 anni). Verifico "on" nel 2023.
    entries = [_entry(date(2018, 1, 1), "1000")]
    result = build_loss_pocket(entries, _RULESET_2024, on=date(2023, 1, 1))
    assert len(result.rows) == 1
    assert result.rows[0].is_expired is True
    assert result.totals_by_perimeter == {}


def test_non_expired_entry_included_in_total():
    entries = [_entry(date(2022, 1, 1), "1000")]
    result = build_loss_pocket(entries, _RULESET_2024, on=date(2023, 1, 1))
    assert result.rows[0].is_expired is False
    assert result.rows[0].expires_on == date(2026, 12, 31)
    assert result.totals_by_perimeter["dichiarativo"] == Decimal("1000.00")


def test_perimeters_are_kept_separate():
    entries = [
        _entry(date(2022, 1, 1), "1000", perimeter="dichiarativo"),
        _entry(date(2022, 1, 1), "500", perimeter="account-a"),
    ]
    result = build_loss_pocket(entries, _RULESET_2024, on=date(2023, 1, 1))
    assert result.totals_by_perimeter == {"dichiarativo": Decimal("1000.00"), "account-a": Decimal("500.00")}


def test_nominal_is_never_mutated_by_the_conversion():
    entries = [_entry(date(2011, 1, 1), "1000")]
    result = build_loss_pocket(entries, _RULESET_2024, on=date(2015, 1, 1))
    row = result.rows[0]
    assert row.nominal == Decimal("1000")
    assert row.usable_amount == Decimal("480.80")
    assert row.coefficient == Decimal("0.4808")

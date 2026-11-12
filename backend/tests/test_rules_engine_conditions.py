"""Regole con piu' condizioni (E/O), condizione sull'importo e regex sicura."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.rules_engine import (
    Condition,
    Probe,
    RuleSpec,
    check_regex_safety,
    conditions_from_json,
    evaluate,
)

_CATEGORY = uuid.uuid4()


def _rule(conditions, match_mode="all") -> RuleSpec:
    return RuleSpec(
        id=uuid.uuid4(),
        conditions=tuple(conditions),
        match_mode=match_mode,
        category_id=_CATEGORY,
        priority=100,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _row(description="Pagamento", amount=None) -> Probe:
    return Probe(description_raw=description, description_normalized=None, merchant=None, amount=amount)


def _text(value) -> Condition:
    return Condition(field="description", operator="contains", value=value)


def _amount(min_amount=None, max_amount=None) -> Condition:
    return Condition(
        field="amount",
        operator="between",
        min_amount=None if min_amount is None else Decimal(min_amount),
        max_amount=None if max_amount is None else Decimal(max_amount),
    )


def test_all_mode_requires_every_condition():
    rule = _rule([_text("rata"), _text("mutuo")])
    assert evaluate([rule], _row("Bonifico Rata Mutuo")) == _CATEGORY
    assert evaluate([rule], _row("Bonifico Rata auto")) is None


def test_any_mode_requires_at_least_one_condition():
    rule = _rule([_text("netflix"), _text("spotify")], match_mode="any")
    assert evaluate([rule], _row("SPOTIFY AB")) == _CATEGORY
    assert evaluate([rule], _row("Lidl")) is None


def test_amount_condition_compares_the_absolute_value():
    rule = _rule([_text("mutuo"), _amount("450", "520")])
    assert evaluate([rule], _row("Rata Mutuo", Decimal("-487.30"))) == _CATEGORY
    assert evaluate([rule], _row("Rata Mutuo", Decimal("487.30"))) == _CATEGORY
    assert evaluate([rule], _row("Rata Mutuo", Decimal("-900"))) is None


def test_amount_condition_never_matches_without_an_amount():
    assert evaluate([_rule([_amount("1", None)])], _row()) is None


def test_amount_condition_open_ended_bounds():
    assert evaluate([_rule([_amount("100", None)])], _row(amount=Decimal("-150"))) == _CATEGORY
    assert evaluate([_rule([_amount("100", None)])], _row(amount=Decimal("-50"))) is None
    assert evaluate([_rule([_amount(None, "100")])], _row(amount=Decimal("-50"))) == _CATEGORY


def test_rule_without_conditions_never_matches():
    assert evaluate([_rule([])], _row()) is None


def test_conditions_from_json_round_trip():
    parsed = conditions_from_json(
        [
            {"field": "description", "operator": "contains", "value": "x"},
            {"field": "amount", "operator": "between", "min": "450", "max": None},
        ]
    )
    assert parsed[0] == Condition(field="description", operator="contains", value="x")
    assert parsed[1].min_amount == Decimal("450") and parsed[1].max_amount is None


def test_regex_safety_accepts_plain_patterns():
    check_regex_safety(r"rata\s+mutuo")


@pytest.mark.parametrize("bad", ["(a+)+$", "(.*)*x", "x" * 201, "[unterminated"])
def test_regex_safety_rejects_dangerous_or_invalid_patterns(bad):
    with pytest.raises(ValueError):
        check_regex_safety(bad)

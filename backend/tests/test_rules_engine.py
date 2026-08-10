import uuid
from datetime import UTC, datetime

from app.services.rules_engine import Probe, RuleSpec, evaluate

_CATEGORY_A = uuid.uuid4()
_CATEGORY_B = uuid.uuid4()


def _rule(**overrides) -> RuleSpec:
    defaults = dict(
        id=uuid.uuid4(),
        field="description",
        operator="contains",
        value="netflix",
        category_id=_CATEGORY_A,
        priority=100,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return RuleSpec(**defaults)


def _row(**overrides) -> Probe:
    defaults = dict(description_raw="Pagamento NETFLIX.COM", description_normalized=None, merchant=None)
    defaults.update(overrides)
    return Probe(**defaults)


def test_equals_is_case_insensitive_and_strips_whitespace():
    rule = _rule(operator="equals", value=" netflix ")
    assert evaluate([rule], _row(description_raw="NetFlix")) == _CATEGORY_A
    assert evaluate([rule], _row(description_raw="netflix extra")) is None


def test_contains():
    rule = _rule(operator="contains", value="netflix")
    assert evaluate([rule], _row(description_raw="Pagamento NETFLIX.COM")) == _CATEGORY_A
    assert evaluate([rule], _row(description_raw="Lidl")) is None


def test_starts_with_and_ends_with():
    starts = _rule(operator="starts_with", value="pagamento")
    ends = _rule(operator="ends_with", value=".com")
    assert evaluate([starts], _row(description_raw="Pagamento Netflix")) == _CATEGORY_A
    assert evaluate([ends], _row(description_raw="netflix.com")) == _CATEGORY_A
    assert evaluate([ends], _row(description_raw="netflix.com extra")) is None


def test_regex_case_insensitive():
    rule = _rule(operator="regex", value=r"^net.lix")
    assert evaluate([rule], _row(description_raw="NETFLIX pagamento")) == _CATEGORY_A


def test_merchant_equals_targets_merchant_column_not_description():
    rule = _rule(operator="merchant_equals", field="merchant", value="Netflix")
    assert evaluate([rule], _row(merchant="netflix")) == _CATEGORY_A
    # anche se la descrizione contiene la parola, senza merchant valorizzato non deve matchare
    assert evaluate([rule], _row(description_raw="netflix", merchant=None)) is None


def test_description_field_falls_back_to_raw_when_normalized_missing():
    rule = _rule(operator="contains", value="lidl")
    row = Probe(description_raw="Supermercato LIDL", description_normalized=None, merchant=None)
    assert evaluate([rule], row) == _CATEGORY_A


def test_description_field_prefers_normalized_when_present():
    rule = _rule(operator="equals", value="lidl milano")
    row = Probe(description_raw="LIDL   MILANO", description_normalized="lidl milano", merchant=None)
    assert evaluate([rule], row) == _CATEGORY_A


def test_first_match_by_priority_wins():
    low_priority = _rule(priority=10, operator="contains", value="lidl", category_id=_CATEGORY_A)
    high_priority = _rule(priority=1, operator="contains", value="lidl", category_id=_CATEGORY_B)
    row = _row(description_raw="Supermercato Lidl")
    assert evaluate([low_priority, high_priority], row) == _CATEGORY_B


def test_priority_tie_broken_by_created_at():
    older = _rule(
        priority=5,
        operator="contains",
        value="lidl",
        category_id=_CATEGORY_A,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = _rule(
        priority=5,
        operator="contains",
        value="lidl",
        category_id=_CATEGORY_B,
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    row = _row(description_raw="Supermercato Lidl")
    assert evaluate([newer, older], row) == _CATEGORY_A


def test_no_active_rules_matches_returns_none():
    rule = _rule(operator="equals", value="lidl")
    assert evaluate([rule], _row(description_raw="Farmacia")) is None
    assert evaluate([], _row()) is None

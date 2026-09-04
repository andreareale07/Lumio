"""Invarianti sul dato puro `IT_RULESETS` (SPEC_TAX_REGIME.md FETTA 1) —
nessun DB. Se uno di questi test fallisce, il regolamento e' internamente
inconsistente prima ancora di arrivare al motore di calcolo."""
from decimal import Decimal

from app.tax.rulesets.italy import IT_RULESETS


def test_rulesets_are_contiguous_and_non_overlapping():
    ordered = sorted(IT_RULESETS, key=lambda r: r.valid_from)
    assert ordered[0].valid_until is not None
    for prev, nxt in zip(ordered, ordered[1:]):
        assert prev.valid_until == nxt.valid_from
    assert ordered[-1].valid_until is None


def test_every_codified_treatment_has_rate_and_legal_reference():
    for ruleset in IT_RULESETS:
        for t in ruleset.treatments:
            if t.status == "codified":
                assert t.rate is not None
                assert t.legal_reference


def test_every_not_codified_treatment_has_no_rate():
    for ruleset in IT_RULESETS:
        for t in ruleset.treatments:
            if t.status == "not_codified":
                assert t.rate is None


def test_every_assumption_has_marker_note():
    for ruleset in IT_RULESETS:
        if ruleset.carry_forward.assumption:
            assert "FISCAL ASSUMPTION REQUIRING VALIDATION" in ruleset.carry_forward.assumption_note
        for t in ruleset.treatments:
            if t.assumption:
                assert "FISCAL ASSUMPTION REQUIRING VALIDATION" in t.assumption_note


def test_titoli_stato_effective_rate_matches_12_5_percent_within_tolerance():
    ruleset = next(r for r in IT_RULESETS if r.code == "IT-2014-07")
    treatment = ruleset.treatment_for("titoli_stato_whitelist", "sale")
    effective = treatment.rate * treatment.taxable_coefficient
    assert abs(effective - Decimal("0.125")) < Decimal("1e-5")


def test_loss_conversion_coefficients_are_legal_values_not_the_exact_fraction():
    ruleset = next(r for r in IT_RULESETS if r.code == "IT-2014-07")
    coefficients = {c.coefficient for c in ruleset.loss_conversions}
    assert Decimal("0.4808") in coefficients
    assert Decimal("0.7692") in coefficients

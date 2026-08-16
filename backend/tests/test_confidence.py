from decimal import Decimal

from app.services.confidence import compute_ai_confidence, needs_review


def test_uses_default_when_provider_declares_no_confidence():
    assert compute_ai_confidence(None, has_merchant=True) == Decimal("0.50")


def test_discounts_when_no_merchant_recognized():
    score = compute_ai_confidence(0.9, has_merchant=False)
    assert score < Decimal("0.90")
    assert score == Decimal("0.77")


def test_no_discount_when_merchant_recognized():
    assert compute_ai_confidence(0.9, has_merchant=True) == Decimal("0.90")


def test_clamps_out_of_range_confidence():
    assert compute_ai_confidence(1.5, has_merchant=True) == Decimal("1.00")
    assert compute_ai_confidence(-0.3, has_merchant=True) == Decimal("0.00")


def test_needs_review_below_threshold():
    assert needs_review(Decimal("0.55"), threshold=0.6) is True


def test_needs_review_at_or_above_threshold_is_false():
    assert needs_review(Decimal("0.60"), threshold=0.6) is False
    assert needs_review(Decimal("0.95"), threshold=0.6) is False


def test_needs_review_deterministic_scores_never_flag_with_default_threshold():
    # Le uscite deterministiche (rule=1.00, system/type_map=1.00,
    # catalogo=0.95) non devono mai finire "da verificare" con la soglia
    # di default — solo l'AI produce punteggi abbastanza bassi da farlo.
    assert needs_review(Decimal("1.00"), threshold=0.6) is False
    assert needs_review(Decimal("0.95"), threshold=0.6) is False

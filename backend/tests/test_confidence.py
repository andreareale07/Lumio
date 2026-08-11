from decimal import Decimal

from app.services.confidence import compute_ai_confidence


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

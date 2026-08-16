from app.services.investment_strategy import classify_strategy


def test_recognizes_pac_installment():
    assert classify_strategy("Savings plan execution") == "recurring_plan"


def test_recognizes_one_off_trades():
    assert classify_strategy("Buy trade") == "one_off"
    assert classify_strategy("Sell trade") == "one_off"


def test_case_and_whitespace_insensitive():
    assert classify_strategy("  SAVINGS PLAN EXECUTION  ") == "recurring_plan"


def test_unknown_or_missing_label_falls_back_to_other_never_a_guess():
    assert classify_strategy("Qualcos'altro") == "other"
    assert classify_strategy(None) == "other"

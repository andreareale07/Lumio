"""Test unitari della matematica pura di `recurrence_calc.py` (piano
`synchronous-chasing-pike.md`, FETTA 2) — nessuna dipendenza da DB, stesso
stile di `test_analytics_calc.py`."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.services.recurrence_calc import (
    Occurrence,
    detect_price_change,
    detect_series,
    series_key_for,
    series_token,
)

_DIRECTION = "expense"


def _occ(d: date, amount: str, *, label="Netflix", currency="EUR", category_id=None, series_key=None):
    key = series_key or series_key_for(_DIRECTION, label)
    return Occurrence(
        transaction_id=uuid.uuid4(),
        occurrence_date=d,
        series_key=key,
        label=label,
        amount=Decimal(amount),
        currency=currency,
        category_id=category_id,
    )


def _monthly_dates(start: date, count: int) -> list[date]:
    dates = []
    y, m = start.year, start.month
    for i in range(count):
        month = (m - 1 + i) % 12 + 1
        year = y + (m - 1 + i) // 12
        dates.append(date(year, month, min(start.day, 28)))
    return dates


def test_series_token_prefers_merchant_over_description():
    assert series_token("Netflix", "PAGAMENTO POS NETFLIX.COM 123456") == "Netflix"


def test_series_token_falls_back_to_extract_merchant():
    token = series_token(None, "PAGAMENTO POS SPOTIFY AB 30/09")
    assert token is not None
    assert "SPOTIFY" in token.upper()


def test_series_token_discards_digit_subtokens():
    token = series_token("Ordine 4821 Amazon", "irrelevant")
    assert token is not None
    assert "4821" not in token


def test_series_key_stable_for_same_direction_and_token():
    assert series_key_for("expense", "Netflix") == series_key_for("expense", "Netflix")


def test_series_key_normalizes_case_and_accents():
    assert series_key_for("expense", "Città") == series_key_for("expense", "CITTA")


def test_series_key_differs_by_direction():
    assert series_key_for("expense", "Netflix") != series_key_for("income", "Netflix")


def test_monthly_regular_subscription_detected():
    dates = _monthly_dates(date(2025, 1, 15), 8)
    occurrences = [_occ(d, "12.99") for d in dates]
    as_of = dates[-1] + timedelta(days=10)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    series = result[0]
    assert series.cadence == "monthly"
    assert series.confidence == "medium"
    assert series.status == "active"
    assert series.typical_amount == Decimal("12.99")


def test_price_change_detected_and_expected_next_amount_updated():
    dates = _monthly_dates(date(2025, 1, 15), 12)
    amounts = ["12.99"] * 6 + ["14.99"] * 6
    occurrences = [_occ(d, a) for d, a in zip(dates, amounts)]
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    series = result[0]
    assert series.price_change is not None
    assert series.price_change.old_amount == Decimal("12.99")
    assert series.price_change.new_amount == Decimal("14.99")
    assert series.expected_next_amount == Decimal("14.99")


def test_weekend_slippage_within_tolerance_still_matches():
    # Date "vere" (banca che addebita il giorno lavorativo piu' vicino al
    # 3 del mese): ogni scostamento resta entro la tolleranza mensile (4
    # giorni) dallo slot calendariale, ma nessuna e' esattamente il 3.
    shifted = [date(2025, 1, 5), date(2025, 1, 31), date(2025, 3, 4), date(2025, 4, 1), date(2025, 5, 6), date(2025, 6, 3)]
    occurrences = [_occ(d, "9.99") for d in shifted]
    as_of = shifted[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    assert result[0].cadence == "monthly"
    assert result[0].occurrences_count == 6


def test_end_of_month_billing_uses_add_months_clamped():
    dates = [date(2025, 1, 31), date(2025, 2, 28), date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31)]
    occurrences = [_occ(d, "50.00") for d in dates]
    as_of = dates[-1] + timedelta(days=3)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    assert result[0].cadence == "monthly"
    assert result[0].occurrences_count == 5


def test_28_day_cadence_detected_as_four_weekly_not_monthly():
    start = date(2025, 1, 5)
    dates = [start + timedelta(days=28 * i) for i in range(8)]
    occurrences = [_occ(d, "5.00") for d in dates]
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    assert result[0].cadence == "four_weekly"


def test_quarterly_cadence_detected():
    dates = [date(2024, 1, 10), date(2024, 4, 10), date(2024, 7, 10), date(2024, 10, 10), date(2025, 1, 10)]
    occurrences = [_occ(d, "120.00") for d in dates]
    as_of = dates[-1] + timedelta(days=10)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    assert result[0].cadence == "quarterly"


def test_annual_cadence_with_two_occurrences_is_medium_confidence():
    dates = [date(2024, 3, 1), date(2025, 3, 1)]
    occurrences = [_occ(d, "300.00") for d in dates]
    as_of = dates[-1] + timedelta(days=10)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    assert result[0].cadence == "annual"
    assert result[0].confidence == "medium"


def test_two_monthly_occurrences_not_enough_to_detect():
    dates = _monthly_dates(date(2025, 1, 15), 2)
    occurrences = [_occ(d, "12.99") for d in dates]
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert result == []


def test_irregular_grocery_shopping_rejected_extras_exceed_matched():
    start = date(2025, 1, 1)
    dates = [start + timedelta(days=3 * i) for i in range(40)]
    occurrences = [_occ(d, "35.00", label="Supermercato") for d in dates]
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert result == []


def test_ended_when_recent_data_exists_but_series_stopped():
    dates = _monthly_dates(date(2024, 1, 15), 6)
    occurrences = [_occ(d, "9.99") for d in dates]
    last_seen = dates[-1]
    as_of = last_seen + timedelta(days=100)
    # C'e' attivita' recente nel workspace (altre transazioni della stessa
    # direzione) fino a `as_of`: la serie e' davvero terminata.
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    assert result[0].status == "ended"


def test_active_when_no_recent_data_ghost_months_guard():
    dates = _monthly_dates(date(2024, 1, 15), 6)
    occurrences = [_occ(d, "9.99") for d in dates]
    last_seen = dates[-1]
    as_of = last_seen + timedelta(days=100)
    # L'ultimo import del workspace si e' fermato proprio a `last_seen`
    # (nessun dato piu' recente): non si puo' dire che la serie sia
    # terminata solo perche' non c'e' stato nessun nuovo import.
    result = detect_series(occurrences, as_of, data_coverage_end=last_seen)
    assert len(result) == 1
    assert result[0].status == "active"


def test_variable_bill_no_spurious_price_change():
    dates = _monthly_dates(date(2025, 1, 15), 10)
    amounts = ["45.00", "52.00", "38.00", "60.00", "41.00", "55.00", "47.00", "39.00", "58.00", "44.00"]
    occurrences = [_occ(d, a, label="Bolletta Luce") for d, a in zip(dates, amounts)]
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    series = result[0]
    assert series.amount_is_variable is True
    assert series.price_change is None


def test_salary_with_december_bonus_no_spurious_price_change():
    dates = _monthly_dates(date(2024, 1, 27), 12)
    amounts = ["2000.00"] * 11 + ["4000.00"]
    occurrences = [
        _occ(d, a, label="Stipendio") for d, a in zip(dates, amounts)
    ]
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    series = result[0]
    assert series.cadence == "monthly"
    assert series.amount_is_variable is True
    assert series.price_change is None


def test_key_stability_with_null_merchant_falls_back_to_extract_merchant():
    # `extract_merchant("PAGAMENTO POS SPOTIFY 12345678")` produce lo stesso
    # token "Spotify" del merchant gia' valorizzato — una riclassificazione
    # futura (che valorizza `merchant`) non fa quindi cambiare la chiave.
    key_with_merchant = series_key_for("expense", series_token("Spotify", "irrelevant"))
    key_without_merchant = series_key_for(
        "expense", series_token(None, "PAGAMENTO POS SPOTIFY 12345678")
    )
    assert key_with_merchant == key_without_merchant


def test_double_import_duplicate_collapsed_before_cadence_test():
    dates = _monthly_dates(date(2025, 1, 15), 6)
    occurrences = [_occ(d, "12.99") for d in dates]
    # Duplica la prima occorrenza (stessa data, stesso importo — import
    # doppio): non deve gonfiare `occurrences_count` ne' rompere il test.
    occurrences.append(_occ(dates[0], "12.99", series_key=occurrences[0].series_key))
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    assert result[0].occurrences_count == 6


def test_multi_currency_series_flagged_and_suppresses_price_change():
    dates = _monthly_dates(date(2025, 1, 15), 6)
    occurrences = []
    for i, d in enumerate(dates):
        currency = "CHF" if i >= 3 else "EUR"
        occurrences.append(_occ(d, "12.99" if i < 3 else "14.99", currency=currency))
    as_of = dates[-1] + timedelta(days=5)
    result = detect_series(occurrences, as_of, data_coverage_end=as_of)
    assert len(result) == 1
    series = result[0]
    assert series.multi_currency is True
    assert series.price_change is None


def test_detect_price_change_returns_none_when_stable():
    dates = _monthly_dates(date(2025, 1, 15), 6)
    amounts = [(d, Decimal("12.99")) for d in dates]
    assert detect_price_change(amounts) is None


def test_detect_price_change_rejects_isolated_spike():
    dates = _monthly_dates(date(2025, 1, 15), 8)
    values = ["12.99"] * 4 + ["30.00"] + ["12.99"] * 3
    amounts = [(d, Decimal(v)) for d, v in zip(dates, values)]
    # Il picco isolato non resta stabile dopo di se': non e' un repricing.
    assert detect_price_change(amounts) is None

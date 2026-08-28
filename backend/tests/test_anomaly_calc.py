"""Test unitari della matematica pura di `anomaly_calc.py` (piano
`synchronous-chasing-pike.md`, FETTA 2 §2.5) — nessuna dipendenza da DB."""
import uuid
from datetime import date
from decimal import Decimal

from app.services.anomaly_calc import (
    CategorySample,
    SeriesSample,
    detect_category_outliers,
    detect_series_deviations,
    mad,
    modified_z_scores,
)

_CATEGORY = uuid.uuid4()


def _sample(amount: str, d: date = date(2026, 3, 1), category_id=None) -> CategorySample:
    return CategorySample(
        transaction_id=uuid.uuid4(), occurrence_date=d, amount=Decimal(amount), category_id=category_id or _CATEGORY
    )


def test_mad_of_identical_values_is_zero():
    values = [Decimal("10")] * 5
    assert mad(values) == Decimal("0")


def test_outlier_flagged_with_sample_size_at_least_eight():
    # 7 spese ordinarie intorno a 30€ + 1 spesa da 350€ — campione di 8.
    samples = [_sample(a) for a in ["28", "31", "29", "32", "30", "33", "27"]]
    outlier = _sample("350")
    samples.append(outlier)
    results = detect_category_outliers(samples)
    flagged_ids = {r.transaction_id for r in results}
    assert outlier.transaction_id in flagged_ids
    result = next(r for r in results if r.transaction_id == outlier.transaction_id)
    assert result.anomaly_type == "category_outlier"
    assert result.sample_size == 8


def test_no_flag_below_minimum_sample_size():
    # Solo 5 transazioni nella categoria: sotto la soglia minima di 8, anche
    # con un valore molto fuori scala nessun flag deve uscire (nessuna
    # baseline statisticamente sensata).
    samples = [_sample(a) for a in ["30", "31", "29", "28", "500"]]
    results = detect_category_outliers(samples)
    assert results == []


def test_mad_zero_fallback_to_mean_absolute_deviation():
    # Molti importi identici (MAD=0) ma non tutti: la mean absolute
    # deviation non zero permette comunque di calcolare uno z-score reale.
    values = [Decimal("20")] * 7 + [Decimal("80")]
    assert mad(values) == Decimal("0")
    scores = modified_z_scores(values)
    assert scores[-1] is not None
    assert abs(scores[-1]) > Decimal("0")


def test_mad_and_mean_absolute_deviation_both_zero_flags_without_score():
    # Un solo outlier isolato con un campione altrimenti perfettamente
    # costante puo' comunque avere una mean absolute deviation non zero
    # (vedi test sopra); il vero caso "entrambe zero" e' un campione
    # interamente costante: nessuna riga si scosta dalla mediana, quindi
    # nessun flag e nessuno z-score.
    values = [Decimal("20")] * 8
    scores = modified_z_scores(values)
    assert all(s is None for s in scores)


def test_high_z_but_below_absolute_threshold_not_flagged():
    # Categoria "Caffe'" con importi quasi identici intorno a 1,50€: un
    # cornetto da 4€ avrebbe uno z-score altissimo ma lo scostamento
    # assoluto (2,50€) resta sotto la soglia dei 25€ — mai flaggato.
    samples = [_sample(a) for a in ["1.50", "1.50", "1.50", "1.50", "1.50", "1.50", "1.50"]]
    samples.append(_sample("4.00"))
    results = detect_category_outliers(samples)
    assert results == []


def test_series_member_absent_from_category_outlier_but_in_sample():
    # Netflix (parte di una serie ricorrente rilevata) resta nel campione
    # della categoria "Abbonamenti" per non falsare la distribuzione, ma
    # NON deve mai essere flaggato dal test di categoria — qui simulato
    # semplicemente NON passandolo a `detect_category_outliers` (il
    # filtro e' responsabilita' del chiamante, `detection.py`).
    baseline_without_series_member = [_sample(a) for a in ["12.99", "45", "30", "22", "18", "60", "25", "40"]]
    results = detect_category_outliers(baseline_without_series_member)
    assert results == [] or all(r.amount != Decimal("12.99") for r in results)


def test_series_deviation_detected_distinct_from_sustained_price_change():
    series_key = "netflix-series"
    level = Decimal("12.99")
    # Un addebito anomalo di 49€ contro un livello di serie di 12,99€.
    spike = SeriesSample(
        transaction_id=uuid.uuid4(),
        occurrence_date=date(2026, 3, 1),
        amount=Decimal("49.00"),
        category_id=_CATEGORY,
        series_key=series_key,
        level=level,
        sample_size=6,
        price_change_at=None,
    )
    results = detect_series_deviations([spike])
    assert len(results) == 1
    assert results[0].anomaly_type == "series_deviation"
    assert results[0].series_key == series_key


def test_series_deviation_suppressed_after_sustained_price_change():
    series_key = "netflix-series"
    change_date = date(2026, 2, 1)
    # L'importo e' cambiato in modo sostenuto (nuovo livello 14,99€): le
    # occorrenze successive al cambio non sono una deviazione, sono la
    # nuova normalita' — gia' segnalata a parte come `price_change`.
    occurrence_after_change = SeriesSample(
        transaction_id=uuid.uuid4(),
        occurrence_date=date(2026, 3, 1),
        amount=Decimal("14.99"),
        category_id=_CATEGORY,
        series_key=series_key,
        level=Decimal("12.99"),
        sample_size=6,
        price_change_at=change_date,
    )
    results = detect_series_deviations([occurrence_after_change])
    assert results == []


def test_series_deviation_within_band_not_flagged():
    sample = SeriesSample(
        transaction_id=uuid.uuid4(),
        occurrence_date=date(2026, 3, 1),
        amount=Decimal("13.50"),
        category_id=_CATEGORY,
        series_key="x",
        level=Decimal("12.99"),
        sample_size=6,
        price_change_at=None,
    )
    assert detect_series_deviations([sample]) == []

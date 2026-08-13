"""Test unitari della matematica pura di `analytics_calc.py` (rework
UX/design, slice 1: navigazione temporale) — nessuna dipendenza da DB/
FastAPI, come `test_position_calc.py` per il dominio Portfolio. Copre in
particolare la granularita' "semester", aggiunta in questo slice: Postgres
non ha un `date_trunc('semester', ...)` nativo, quindi la coerenza tra il
calcolo puro Python qui testato e l'espressione SQL equivalente
(`app/services/analytics._bucket_expr`) va garantita a mano.
"""
from datetime import date

from app.services.analytics_calc import GRANULARITIES, _bucket_start, _next_bucket, generate_buckets


def test_granularities_include_semester():
    assert "semester" in GRANULARITIES


def test_bucket_start_semester_first_half():
    assert _bucket_start(date(2026, 3, 15), "semester") == date(2026, 1, 1)


def test_bucket_start_semester_second_half():
    assert _bucket_start(date(2026, 7, 1), "semester") == date(2026, 7, 1)
    assert _bucket_start(date(2026, 12, 31), "semester") == date(2026, 7, 1)


def test_next_bucket_semester_rolls_over_to_next_year():
    assert _next_bucket(date(2026, 7, 1), "semester") == date(2027, 1, 1)


def test_next_bucket_semester_within_same_year():
    assert _next_bucket(date(2026, 1, 1), "semester") == date(2026, 7, 1)


def test_generate_buckets_semester_two_buckets_same_year():
    buckets = generate_buckets(date(2026, 1, 15), date(2026, 8, 20), "semester")
    assert buckets == [date(2026, 1, 1), date(2026, 7, 1)]


def test_generate_buckets_semester_spanning_year_boundary():
    buckets = generate_buckets(date(2025, 8, 1), date(2026, 2, 1), "semester")
    assert buckets == [date(2025, 7, 1), date(2026, 1, 1)]

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.analytics import PeriodOut

RECURRING_CADENCES = ("monthly", "four_weekly", "quarterly", "annual")
RECURRING_STATUSES = ("active", "ended")
ANOMALY_TYPES = ("category_outlier", "series_deviation")


class RecurringOccurrenceOut(BaseModel):
    transaction_id: uuid.UUID
    transaction_date: date
    amount: Decimal | None


class RecurringPriceChangeOut(BaseModel):
    changed_at: date
    old_amount: Decimal
    new_amount: Decimal


class RecurringSeriesItemOut(BaseModel):
    series_key: str
    label: str
    cadence: str
    status: str
    confidence: str
    occurrences_count: int
    first_seen: date
    last_seen: date
    expected_next_date: date
    expected_next_amount: Decimal | None
    typical_amount: Decimal | None
    monthly_equivalent: Decimal | None
    amount_is_variable: bool
    price_change: RecurringPriceChangeOut | None
    category_id: uuid.UUID | None
    category_name: str | None
    multi_currency: bool
    has_unconverted_rows: bool
    occurrences: list[RecurringOccurrenceOut]


class RecurringSeriesListOut(BaseModel):
    currency: str
    direction: str
    as_of: date
    analysis_window: PeriodOut
    monthly_total: Decimal
    items: list[RecurringSeriesItemOut]
    # Nessuna serie rilevabile con affidabilita' (workspace troppo giovane,
    # < ~60 giorni di storico nella finestra di analisi) — mai una lista
    # vuota indistinguibile da "nessun abbonamento".
    insufficient_data: bool
    has_unconverted_rows: bool


class AnomalyItemOut(BaseModel):
    transaction_id: uuid.UUID
    transaction_date: date
    label: str
    amount: Decimal
    currency: str
    anomaly_type: str
    category_id: uuid.UUID | None
    category_name: str | None
    baseline_amount: Decimal
    deviation_amount: Decimal
    deviation_pct: Decimal | None
    robust_score: Decimal | None
    sample_size: int
    series_key: str | None


class AnomalyListOut(BaseModel):
    currency: str
    direction: str
    period: PeriodOut
    # Finestra REALE usata per calcolare mediana/MAD (12 mesi fino a
    # `date_to`) — mai il periodo richiesto, cosi' la UI puo' dire
    # onestamente "rispetto agli ultimi 12 mesi" invece di lasciarlo implicito.
    baseline: PeriodOut
    items: list[AnomalyItemOut]
    insufficient_data: bool
    has_unconverted_rows: bool


class DetectionOverrideIn(BaseModel):
    override_type: Literal["recurring_series", "anomaly"]
    series_key: str | None = None
    transaction_id: uuid.UUID | None = None
    # 'confirmed' e' riservata nel CHECK del DB ma NON scrivibile da questo
    # endpoint in v1 (§2.12 del piano: nessun endpoint la scrive) — l'unico
    # valore che l'API accetta oggi e' 'ignored'.
    decision: Literal["ignored"] = "ignored"


class DetectionOverrideOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    override_type: str
    series_key: str | None
    transaction_id: uuid.UUID | None
    decision: str
    created_at: datetime


__all__ = [
    "RECURRING_CADENCES",
    "RECURRING_STATUSES",
    "ANOMALY_TYPES",
    "RecurringOccurrenceOut",
    "RecurringPriceChangeOut",
    "RecurringSeriesItemOut",
    "RecurringSeriesListOut",
    "AnomalyItemOut",
    "AnomalyListOut",
    "DetectionOverrideIn",
    "DetectionOverrideOut",
]

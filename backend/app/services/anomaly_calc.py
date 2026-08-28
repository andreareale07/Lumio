"""Matematica pura per la rilevazione di anomalie (piano
`synchronous-chasing-pike.md`, FETTA 2 §2.5), nessuna dipendenza da DB/
FastAPI, stesso principio di `recurrence_calc.py`. Il lato DB-aware (query
fx-convertita, baseline a 12 mesi, esclusione delle serie ricorrenti dal
test di categoria) vive in `app/services/detection.py`.

MAD (Median Absolute Deviation), non IQR: breakdown point 50% contro il 25%
di IQR — con 8-20 punti per categoria fortemente asimmetrici, due acquisti
grandi spostano gia' il fence IQR; MAD e' una formula sola, IQR richiede
scegliere fra nove convenzioni di interpolazione dei quantili. Z-score
modificato (Iglewicz-Hoaglin): z = 0,6745 * (x - mediana) / MAD, soglia 3,5.
"""
import statistics
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Campione minimo per categoria (nella finestra baseline di 12 mesi) perche'
# lo z-score abbia senso statistico — un mese solo non ha baseline.
CATEGORY_MIN_SAMPLE = 8
CATEGORY_Z_THRESHOLD = Decimal("3.5")
# Soglia assoluta: senza, un cornetto da 4€ in "Caffe'" finirebbe flaggato a
# z altissimo se la categoria ha importi quasi tutti identici.
CATEGORY_ABS_THRESHOLD = Decimal("25")

# Test di serie (§2.5): piu' stretto, contro il LIVELLO della propria serie
# — cosi' "Netflix ti ha addebitato 49€" si vede anche se 49€ e' ordinario
# dentro "Abbonamenti" (il test di categoria non puo' strutturalmente
# coglierlo).
SERIES_DEVIATION_PCT = Decimal("0.25")
SERIES_DEVIATION_ABS = Decimal("15")


def _median(values: list[Decimal]) -> Decimal:
    return statistics.median(values)


@dataclass(frozen=True)
class CategorySample:
    """Una riga del campione baseline di una categoria (roll-up al padre,
    `category_id IS NULL` gia' escluso dal chiamante — nessuna baseline
    sensata per le transazioni senza categoria)."""

    transaction_id: uuid.UUID
    occurrence_date: date
    amount: Decimal
    category_id: uuid.UUID


@dataclass(frozen=True)
class SeriesSample:
    """Una occorrenza di una serie ricorrente gia' rilevata (§2.5): esclusa
    dal test di categoria dal chiamante, valutata qui contro il livello
    della propria serie. `price_change_at`: se valorizzato, le occorrenze da
    quella data in poi sono la NUOVA normalita' (variazione di prezzo gia'
    segnalata a parte) — mai una deviazione."""

    transaction_id: uuid.UUID
    occurrence_date: date
    amount: Decimal
    category_id: uuid.UUID | None
    series_key: str
    level: Decimal
    sample_size: int
    price_change_at: date | None = None


@dataclass(frozen=True)
class AnomalyResult:
    transaction_id: uuid.UUID
    occurrence_date: date
    amount: Decimal
    category_id: uuid.UUID | None
    anomaly_type: str  # "category_outlier" | "series_deviation"
    baseline_amount: Decimal
    deviation_amount: Decimal
    deviation_pct: Decimal | None
    robust_score: Decimal | None
    sample_size: int
    series_key: str | None = None


def mad(values: list[Decimal]) -> Decimal:
    """Median Absolute Deviation: mediana degli scarti assoluti dalla
    mediana. Puo' essere 0 quando il campione ha molti importi quasi
    identici — il chiamante (`modified_z_scores`) gestisce il fallback."""
    med = _median(values)
    return _median([abs(v - med) for v in values])


def modified_z_scores(values: list[Decimal]) -> list[Decimal | None]:
    """z modificato (Iglewicz-Hoaglin) per ogni valore, stesso ordine di
    `values`. Fallback a due livelli quando MAD == 0 (comune: categoria con
    importi quasi tutti uguali):
    1. mean absolute deviation al posto della MAD;
    2. se ANCHE quella e' 0, nessuno z-score finto: `None` per tutti — il
       chiamante decide il flag confrontando `x` con la mediana direttamente
       (mai un numero inventato mostrato in UI)."""
    if not values:
        return []
    med = _median(values)
    m = mad(values)
    if m != 0:
        return [Decimal("0.6745") * (v - med) / m for v in values]
    mean_abs_dev = sum((abs(v - med) for v in values), Decimal("0")) / len(values)
    if mean_abs_dev != 0:
        return [Decimal("0.6745") * (v - med) / mean_abs_dev for v in values]
    return [None for _ in values]


def detect_category_outliers(samples: list[CategorySample]) -> list[AnomalyResult]:
    """Outlier per categoria (roll-up al padre) sull'INTERO campione
    passato — il chiamante decide la finestra (baseline 12 mesi) e quali
    transazioni escludere perche' gia' membri di una serie ricorrente
    (§2.5: restano nel campione per non falsare la distribuzione, ma non
    possono essere flaggate da QUESTO test)."""
    by_category: dict[uuid.UUID, list[CategorySample]] = {}
    for s in samples:
        by_category.setdefault(s.category_id, []).append(s)

    results: list[AnomalyResult] = []
    for category_id, group in by_category.items():
        if len(group) < CATEGORY_MIN_SAMPLE:
            continue
        values = [g.amount for g in group]
        med = _median(values)
        scores = modified_z_scores(values)
        for sample, score in zip(group, scores):
            deviation = sample.amount - med
            if abs(deviation) < CATEGORY_ABS_THRESHOLD:
                continue
            if score is not None:
                flagged = abs(score) >= CATEGORY_Z_THRESHOLD
            else:
                # MAD e mean-absolute-deviation entrambe 0: flag solo se
                # x != mediana, MAI uno z-score finto (robust_score resta None).
                flagged = sample.amount != med
            if not flagged:
                continue
            deviation_pct = (deviation / med) if med != 0 else None
            results.append(
                AnomalyResult(
                    transaction_id=sample.transaction_id,
                    occurrence_date=sample.occurrence_date,
                    amount=sample.amount,
                    category_id=category_id,
                    anomaly_type="category_outlier",
                    baseline_amount=med,
                    deviation_amount=deviation,
                    deviation_pct=deviation_pct,
                    robust_score=score,
                    sample_size=len(group),
                )
            )
    return results


def detect_series_deviations(samples: list[SeriesSample]) -> list[AnomalyResult]:
    """Deviazione dal livello della propria serie — distinta da una
    variazione di prezzo sostenuta gia' rilevata (`price_change_at`): le
    occorrenze successive a quella data sono la nuova normalita', mai
    riportate come deviazione."""
    results: list[AnomalyResult] = []
    for s in samples:
        if s.price_change_at is not None and s.occurrence_date >= s.price_change_at:
            continue
        if s.level == 0:
            continue
        deviation = s.amount - s.level
        threshold = max(s.level * SERIES_DEVIATION_PCT, SERIES_DEVIATION_ABS)
        if abs(deviation) <= threshold:
            continue
        results.append(
            AnomalyResult(
                transaction_id=s.transaction_id,
                occurrence_date=s.occurrence_date,
                amount=s.amount,
                category_id=s.category_id,
                anomaly_type="series_deviation",
                baseline_amount=s.level,
                deviation_amount=deviation,
                deviation_pct=(deviation / s.level),
                robust_score=None,
                sample_size=s.sample_size,
                series_key=s.series_key,
            )
        )
    return results

"""Matematica pura per gli analytics (SPEC §30, 31, 39, 45, 46), nessuna
dipendenza da DB/FastAPI, unit-testabile in isolamento come `rules_engine.py`.
Il lato DB-aware (query di aggregazione) vive in `app/services/analytics.py`,
che chiama queste funzioni per la parte di calcolo.
"""
from datetime import date, timedelta
from decimal import Decimal

GRANULARITIES = ("day", "week", "month", "quarter", "semester", "year")


def previous_period(date_from: date, date_to: date) -> tuple[date, date]:
    """Periodo immediatamente precedente, della stessa durata (in giorni,
    entrambi gli estremi inclusi), usato per i confronti "vs periodo
    precedente" di KPI Cards e Cash Flow (SPEC_FE §13)."""
    length_days = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=length_days - 1)
    return prev_from, prev_to


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, 1)


def _bucket_start(d: date, granularity: str) -> date:
    if granularity == "day":
        return d
    if granularity == "week":
        return d - timedelta(days=d.weekday())
    if granularity == "month":
        return d.replace(day=1)
    if granularity == "quarter":
        quarter_month = ((d.month - 1) // 3) * 3 + 1
        return d.replace(month=quarter_month, day=1)
    if granularity == "semester":
        return d.replace(month=1 if d.month <= 6 else 7, day=1)
    if granularity == "year":
        return d.replace(month=1, day=1)
    raise ValueError(f"Granularita' non supportata: {granularity}")


def _next_bucket(d: date, granularity: str) -> date:
    if granularity == "day":
        return d + timedelta(days=1)
    if granularity == "week":
        return d + timedelta(days=7)
    if granularity == "month":
        return _add_months(d, 1)
    if granularity == "quarter":
        return _add_months(d, 3)
    if granularity == "semester":
        return _add_months(d, 6)
    if granularity == "year":
        return date(d.year + 1, 1, 1)
    raise ValueError(f"Granularita' non supportata: {granularity}")


def generate_buckets(date_from: date, date_to: date, granularity: str) -> list[date]:
    """Elenco ordinato delle date di inizio-bucket che intersecano
    [date_from, date_to], incluso un bucket parziale in coda/testa se il
    range non e' allineato ai confini del bucket. Serve a riempire con zero
    i bucket senza transazioni: una GROUP BY SQL non produce righe per i
    bucket vuoti, e un grafico con "buchi" e' peggio di un grafico piatto
    a zero."""
    if granularity not in GRANULARITIES:
        raise ValueError(f"Granularita' non supportata: {granularity}")
    if date_from > date_to:
        return []
    buckets = []
    current = _bucket_start(date_from, granularity)
    end = _bucket_start(date_to, granularity)
    while current <= end:
        buckets.append(current)
        current = _next_bucket(current, granularity)
    return buckets


def reconstruct_running_series(
    buckets: list[date], deltas: dict[date, Decimal], current_total: Decimal
) -> list[tuple[date, Decimal]]:
    """Ricostruisce il saldo alla fine di ogni bucket a RITROSO dal saldo
    attuale (`current_total`, alla fine dell'ultimo bucket), sottraendo il
    delta che si e' verificato in ciascun bucket successivo:

        saldo_fine[i] = saldo_fine[i+1] - delta[i+1]

    Andare a ritroso invece che in avanti dall'inizio garantisce che
    l'ultimo punto del grafico coincida sempre col saldo corrente mostrato
    nel KPI accanto, senza bisogno di uno snapshot storico (rimandato a
    M09) né di conoscere il saldo di apertura del conto.
    """
    if not buckets:
        return []
    n = len(buckets)
    balances = [Decimal("0")] * n
    balances[-1] = current_total
    for i in range(n - 2, -1, -1):
        next_bucket = buckets[i + 1]
        delta_next = deltas.get(next_bucket, Decimal("0"))
        balances[i] = balances[i + 1] - delta_next
    return list(zip(buckets, balances))

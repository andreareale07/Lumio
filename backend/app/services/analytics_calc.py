"""Matematica pura per gli analytics (SPEC §30, 31, 39, 45, 46), nessuna
dipendenza da DB/FastAPI, unit-testabile in isolamento come `rules_engine.py`.
Il lato DB-aware (query di aggregazione) vive in `app/services/analytics.py`,
che chiama queste funzioni per la parte di calcolo.
"""
import calendar
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


def add_months_clamped(d: date, months: int) -> date:
    """Aritmetica calendariale per la rilevazione ricorrenze (FETTA 2,
    `recurrence_calc.py`): a differenza di `_add_months` sopra (che scatta
    SEMPRE al giorno 1 del mese risultante — corretto per i bucket, inutile
    per proiettare "prossimo addebito atteso"), preserva il giorno del mese
    e lo CLAMPA all'ultimo giorno valido del mese di destinazione: 31 gennaio
    + 1 mese = 28/29 febbraio (mai 1 marzo, mai un errore)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


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


def forward_fill_daily_series(
    days: list[date], known: dict[date, Decimal], initial: Decimal = Decimal("0")
) -> list[tuple[date, Decimal]]:
    """Forward-fill puro di una serie giornaliera (storico patrimonio
    ricostruito, FETTA 3): ogni giorno SENZA una riga in `known` eredita il
    valore dell'ultimo giorno CON un valore noto (o `initial` se nessun
    giorno precedente ne ha uno) — a differenza di
    `reconstruct_running_series` (che va a RITROSO da un saldo attuale noto,
    usato da `balance_history`), qui si va in AVANTI da un'ancora storica:
    `account_balance_history` produce una riga solo per i giorni con
    attivita' (la query SQL e' un DISTINCT ON per giorno), i giorni senza
    movimenti fra due transazioni vanno riempiti col saldo del giorno
    precedente, mai a zero (un conto senza movimenti per una settimana non
    ha un saldo nullo in quella settimana).

    `initial` e' il saldo del giorno immediatamente prima di `days[0]` (0 se
    il conto non ha alcuna attivita' precedente a quel giorno — coerente col
    fatto che, senza alcuna ancora, la formula del saldo collassa sul
    running sum a partire da zero, vedi `analytics.account_balance_history`).
    """
    result: list[tuple[date, Decimal]] = []
    current = initial
    for day in days:
        if day in known:
            current = known[day]
        result.append((day, current))
    return result

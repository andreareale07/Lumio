"""Matematica pura per la rilevazione di serie ricorrenti (piano
`synchronous-chasing-pike.md`, FETTA 2 — SPEC.md §30 mai implementata prima
d'ora), nessuna dipendenza da DB/FastAPI, stesso principio di
`analytics_calc.py`. Il lato DB-aware (query fx-convertita condivisa,
assemblaggio della risposta API, override utente) vive in
`app/services/detection.py`.

Algoritmo di cadenza: ANCORATO AL CALENDARIO, non sui gap mediani (un gap
mediano non separa un abbonamento a 28 giorni da uno mensile — la deriva
calendariale del 4-settimanale supera la tolleranza mensile entro il 3°
slot indietro, vedi `_TOLERANCE_DAYS`). Si generano a ritroso da
`last_seen` gli slot attesi di ciascuna cadenza candidata, si abbinano alle
occorrenze reali entro tolleranza, si accetta la cadenza col miglior
`match_ratio` fra quelle che passano le soglie (vedi `_detect_one_series`).
"""
import hashlib
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.services.analytics_calc import add_months_clamped
from app.services.merchant_extraction import extract_merchant, normalize_for_matching
from app.services.transaction_dedup import canonical_description_for_fingerprint

CADENCES = ("monthly", "four_weekly", "quarterly", "annual")

# Tolleranza di abbinamento slot<->occorrenza (giorni), assorbe weekend/
# festivi/piccoli slittamenti di addebito bancario.
_TOLERANCE_DAYS = {"monthly": 4, "four_weekly": 4, "quarterly": 7, "annual": 15}
# Occorrenze minime ABBINATE perche' la cadenza sia accettata.
_MIN_OCCURRENCES = {"monthly": 3, "four_weekly": 3, "quarterly": 3, "annual": 2}
_MIN_MATCH_RATIO = Decimal("0.75")
# Durata nominale di un ciclo (giorni), usata solo per decidere "terminata".
_CADENCE_NOMINAL_DAYS = {"monthly": 30, "four_weekly": 28, "quarterly": 91, "annual": 365}
# Occorrenze/anno nominali, per l'equivalente mensile (§2.7 API).
_OCCURRENCES_PER_YEAR = {
    "monthly": Decimal(12),
    "four_weekly": Decimal("365.25") / Decimal(28),
    "quarterly": Decimal(4),
    "annual": Decimal(1),
}
_MONTHS_STEP = {"monthly": 1, "quarterly": 3, "annual": 12}

# Finestra di analisi (mesi indietro da `as_of`) — vedi `detection.py`.
ANALYSIS_WINDOW_MONTHS = 25

# Variazione importo (§2.4): "amount_is_variable" se uno scostamento supera
# questa banda dal livello (mediana). Volutamente DIVERSA dalla soglia
# ±10%/50€ usata per gli aggregati di periodo in Dashboard/Spese (vedi
# lib/stats.ts::isSignificantChange lato frontend) — applicata qui
# sopprimerebbe esattamente il caso d'uso richiesto (Netflix 12,99->14,99).
_VARIABLE_AMOUNT_PCT = Decimal("0.05")
_VARIABLE_AMOUNT_ABS = Decimal("1")

# Variazione di prezzo sostenuta (§2.4): soglia sul salto fra la mediana
# delle <=3 occorrenze precedenti e quella delle <=3 successive.
_PRICE_CHANGE_PCT = Decimal("0.02")
_PRICE_CHANGE_ABS = Decimal("0.50")
_PRICE_CHANGE_WINDOW = 3


@dataclass(frozen=True)
class Occurrence:
    """Una riga movimento gia' assegnata a una chiave di serie (calcolata da
    `series_key_for` dal chiamante DB-aware) — vedi `detection.py::load_movements`.
    `amount` e' GIA' convertito nella valuta target, `None` se la riga non e'
    convertibile (nessun tasso disponibile per quella data/valuta): la
    cadenza resta comunque valutabile sulla sola data, le statistiche di
    importo la escludono (`has_unconverted_rows`)."""

    transaction_id: uuid.UUID
    occurrence_date: date
    series_key: str
    label: str
    amount: Decimal | None
    currency: str
    category_id: uuid.UUID | None


@dataclass(frozen=True)
class PriceChange:
    changed_at: date
    old_amount: Decimal
    new_amount: Decimal


@dataclass
class Series:
    series_key: str
    label: str
    cadence: str
    status: str  # "active" | "ended"
    confidence: str  # sempre "medium" in v1
    occurrences_count: int
    first_seen: date
    last_seen: date
    expected_next_date: date
    expected_next_amount: Decimal | None
    typical_amount: Decimal | None
    monthly_equivalent: Decimal | None
    amount_is_variable: bool
    price_change: PriceChange | None
    category_id: uuid.UUID | None
    multi_currency: bool
    has_unconverted_rows: bool
    occurrences: list[Occurrence] = field(default_factory=list)


def _median(values: list[Decimal]) -> Decimal:
    return statistics.median(values)


def series_token(merchant: str | None, description_raw: str) -> str | None:
    """Token di raggruppamento leggibile (usato anche come `label`
    visualizzata): `merchant` se gia' valorizzato, altrimenti
    `extract_merchant(description_raw)` (stessa funzione del backfill
    merchant, vedi `reclassification_job.py::_backfill_merchant` — una
    riclassificazione futura non fa quindi cambiare la chiave), altrimenti
    il fallback dedup troncato. Scarta i sotto-token che contengono cifre
    (numeri d'ordine a 4-5 cifre sopravvivono alla soglia >=6 di
    `_NOISE_PATTERNS` in `merchant_extraction.py`)."""
    token = merchant or extract_merchant(description_raw)
    if not token:
        canonical = canonical_description_for_fingerprint(description_raw)[:60]
        token = canonical or None
    if not token:
        return None
    cleaned_tokens = [t for t in token.split(" ") if t and not any(c.isdigit() for c in t)]
    cleaned = " ".join(cleaned_tokens).strip()
    return cleaned or None


def series_key_for(direction: str, token: str) -> str:
    """`sha256(f"{direction}|{token}")[:32]` — normalizzato (accenti/maiuscolo)
    prima dell'hash cosi' varianti di caso/accento dello stesso token
    (merchant estratto vs fallback dedup lowercase) collassano sulla stessa
    chiave. `financial_account_id`/`currency` non entrano MAI qui (Netflix
    spostato su un'altra carta resta una serie sola, per costruzione)."""
    normalized = normalize_for_matching(token)
    payload = f"{direction}|{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _step_forward(d: date, cadence: str) -> date:
    if cadence == "four_weekly":
        return d + timedelta(days=28)
    return add_months_clamped(d, _MONTHS_STEP[cadence])


def _step_back(d: date, cadence: str) -> date:
    if cadence == "four_weekly":
        return d - timedelta(days=28)
    return add_months_clamped(d, -_MONTHS_STEP[cadence])


def _generate_slots(last_seen: date, first_seen: date, cadence: str, tolerance_days: int) -> list[date]:
    """Slot attesi a ritroso da `last_seen`, SOLO fino a `first_seen` (mai
    prima — cio' che evita di segnare come "mancati" i mesi precedenti al
    primo import, vedi guardia mesi-fantasma del CHANGELOG del piano). Il
    cutoff usa la STESSA tolleranza dell'abbinamento (non `first_seen`
    esatta): l'aritmetica calendariale clampata (`add_months_clamped`, es.
    31 gen -> 28 feb) puo' far "scivolare" lo slot piu' vecchio di qualche
    giorno prima di `first_seen` anche quando la prima occorrenza reale E'
    quello slot — senza il margine, la prima occorrenza della serie
    perderebbe sistematicamente il proprio abbinamento."""
    cutoff = first_seen - timedelta(days=tolerance_days)
    slots = []
    current = last_seen
    while current >= cutoff:
        slots.append(current)
        current = _step_back(current, cadence)
    return slots


def _collapse_duplicates(occurrences: list[Occurrence]) -> list[Occurrence]:
    """Import doppio (§2.10): occorrenze con stessa data, stesso importo
    arrotondato E stessa valuta collassate a una — collasso di SOLA LETTURA
    per il test di cadenza, non tocca ne' nasconde nulla al motore di dedup
    (che resta l'unica autorita' su cosa esiste davvero in `transactions`)."""
    seen: dict[tuple, Occurrence] = {}
    for occ in sorted(occurrences, key=lambda o: o.occurrence_date):
        amount_key = occ.amount.quantize(Decimal("0.01")) if occ.amount is not None else None
        key = (occ.occurrence_date, amount_key, occ.currency)
        if key not in seen:
            seen[key] = occ
    return sorted(seen.values(), key=lambda o: o.occurrence_date)


def _match_slots(
    slots: list[date], occurrences: list[Occurrence], tolerance_days: int
) -> tuple[int, set[uuid.UUID]]:
    """Abbinamento greedy slot->occorrenza piu' vicina entro tolleranza, MAI
    la stessa occorrenza per due slot. Ritorna (matched_count, id delle
    occorrenze usate)."""
    used: set[uuid.UUID] = set()
    matched = 0
    for slot in slots:
        best: Occurrence | None = None
        best_diff: int | None = None
        for occ in occurrences:
            if occ.transaction_id in used:
                continue
            diff = abs((occ.occurrence_date - slot).days)
            if diff <= tolerance_days and (best_diff is None or diff < best_diff):
                best = occ
                best_diff = diff
        if best is not None:
            used.add(best.transaction_id)
            matched += 1
    return matched, used


def _monthly_equivalent(amount: Decimal | None, cadence: str) -> Decimal | None:
    if amount is None:
        return None
    return (amount * _OCCURRENCES_PER_YEAR[cadence] / Decimal(12)).quantize(Decimal("0.01"))


def detect_price_change(amounts_by_date: list[tuple[date, Decimal]]) -> PriceChange | None:
    """Ultima variazione di prezzo SOSTENUTA (§2.4): cerca, a ritroso nel
    tempo (cosi' il primo candidato trovato e' cronologicamente l'ULTIMO —
    "si riporta solo l'ultima variazione, non uno storico"), il punto di
    split in cui la mediana delle <=3 occorrenze precedenti e quella delle
    <=3 successive differiscono di oltre max(2%, 0,50€) — E tutte le
    occorrenze da li' in poi restano dentro la banda di stabilita' del
    nuovo livello (distingue un repricing sostenuto da un picco isolato,
    es. una bolletta variabile o uno stipendio con tredicesima a
    dicembre — MAI segnalati qui). `amounts_by_date` deve contenere solo
    occorrenze ABBINATE con importo convertibile, ordinate per data
    crescente."""
    n = len(amounts_by_date)
    for i in range(n - 1, 0, -1):
        before = amounts_by_date[max(0, i - _PRICE_CHANGE_WINDOW) : i]
        after = amounts_by_date[i : i + _PRICE_CHANGE_WINDOW]
        if not before or not after:
            continue
        median_before = _median([a for _, a in before])
        median_after = _median([a for _, a in after])
        threshold = max(median_before * _PRICE_CHANGE_PCT, _PRICE_CHANGE_ABS)
        if abs(median_after - median_before) <= threshold:
            continue
        tail = amounts_by_date[i:]
        stability_band = max(median_after * _VARIABLE_AMOUNT_PCT, _VARIABLE_AMOUNT_ABS)
        if all(abs(a - median_after) <= stability_band for _, a in tail):
            return PriceChange(
                changed_at=amounts_by_date[i][0], old_amount=median_before, new_amount=median_after
            )
    return None


def _detect_one_series(
    series_key: str, group: list[Occurrence], as_of: date, data_coverage_end: date
) -> Series | None:
    collapsed = _collapse_duplicates(group)
    if len(collapsed) < 2:
        return None
    first_seen = collapsed[0].occurrence_date
    last_seen = collapsed[-1].occurrence_date

    best: tuple[Decimal, str, int, set[uuid.UUID]] | None = None
    for cadence in CADENCES:
        slots = _generate_slots(last_seen, first_seen, cadence, _TOLERANCE_DAYS[cadence])
        if not slots:
            continue
        matched, used = _match_slots(slots, collapsed, _TOLERANCE_DAYS[cadence])
        if matched < _MIN_OCCURRENCES[cadence]:
            continue
        extras = len(collapsed) - matched
        if extras > matched:
            continue
        match_ratio = Decimal(matched) / Decimal(len(slots))
        if match_ratio < _MIN_MATCH_RATIO:
            continue
        if best is None or match_ratio > best[0]:
            best = (match_ratio, cadence, matched, used)

    if best is None:
        return None

    _, cadence, _matched, used_ids = best
    matched_occurrences = sorted(
        (o for o in collapsed if o.transaction_id in used_ids), key=lambda o: o.occurrence_date
    )

    convertible = [o for o in matched_occurrences if o.amount is not None]
    currencies = {o.currency for o in matched_occurrences}
    multi_currency = len(currencies) > 1
    has_unconverted_rows = any(o.amount is None for o in matched_occurrences)

    typical_amount = _median([o.amount for o in convertible]) if convertible else None

    amount_is_variable = False
    if typical_amount is not None and convertible:
        band = max(typical_amount * _VARIABLE_AMOUNT_PCT, _VARIABLE_AMOUNT_ABS)
        amount_is_variable = any(abs(o.amount - typical_amount) > band for o in convertible)

    # Variazione di prezzo: SOLO serie a importo fisso, mono-valuta (la
    # deriva FX di una serie multi-valuta sembrerebbe altrimenti un
    # repricing, §2.10).
    price_change = None
    if not amount_is_variable and not multi_currency and convertible:
        by_date = [(o.occurrence_date, o.amount) for o in convertible]
        price_change = detect_price_change(by_date)

    expected_next_amount = price_change.new_amount if price_change is not None else typical_amount
    expected_next_date = _step_forward(last_seen, cadence)

    coverage_end = min(as_of, data_coverage_end)
    status = (
        "ended"
        if (coverage_end - last_seen).days > _CADENCE_NOMINAL_DAYS[cadence] + 2 * _TOLERANCE_DAYS[cadence]
        else "active"
    )

    last_occurrence = matched_occurrences[-1]
    return Series(
        series_key=series_key,
        label=last_occurrence.label,
        cadence=cadence,
        status=status,
        confidence="medium",
        occurrences_count=len(matched_occurrences),
        first_seen=first_seen,
        last_seen=last_seen,
        expected_next_date=expected_next_date,
        expected_next_amount=expected_next_amount,
        typical_amount=typical_amount,
        monthly_equivalent=_monthly_equivalent(typical_amount, cadence),
        amount_is_variable=amount_is_variable,
        price_change=price_change,
        category_id=last_occurrence.category_id,
        multi_currency=multi_currency,
        has_unconverted_rows=has_unconverted_rows,
        occurrences=matched_occurrences,
    )


def detect_series(occurrences: list[Occurrence], as_of: date, data_coverage_end: date) -> list[Series]:
    """Raggruppa `occurrences` per `series_key` e applica il test di cadenza
    a ciascun gruppo (§2.3). `data_coverage_end` e' l'ultima transazione
    REALE del workspace per quella direzione (mai `as_of` da solo: un
    import fermo a 3 mesi fa non deve segnare ogni abbonamento come
    "terminato" — guardia mesi-fantasma, §2.4)."""
    by_key: dict[str, list[Occurrence]] = {}
    for occ in occurrences:
        by_key.setdefault(occ.series_key, []).append(occ)

    results = []
    for series_key, group in by_key.items():
        series = _detect_one_series(series_key, group, as_of, data_coverage_end)
        if series is not None:
            results.append(series)
    return results

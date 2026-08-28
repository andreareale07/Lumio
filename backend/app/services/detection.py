"""Logica DB-aware della rilevazione ricorrenze/anomalie (piano
`synchronous-chasing-pike.md`, FETTA 2), ponte tra l'API
(`app/api/v1/analytics.py`) e le tabelle `transactions`/`categories`/
`detection_overrides` — stessa separazione di `app/services/analytics.py`
fra query DB e matematica pura (`recurrence_calc.py`/`anomaly_calc.py`).

Perche' on-the-fly, nessuna tabella derivata (§2.6 del piano): il risultato
dipende da `transaction_date`/`amount`/`currency`/`merchant`/`category_id`,
mutati da sei percorsi di scrittura diversi (import, modifica manuale,
correzione categoria, riclassificazione, risoluzione dedup, cancellazione
import) — l'invalidazione di una cache sarebbe il costo vero, peggiore del
calcolo. Una query indicizzata (`ix_transactions_workspace_date`, migration
0008) per l'intera finestra di analisi; su un workspace da 10k transazioni
resta nella classe di endpoint gia' serviti in-request (`/analytics/balances`
fa gia' un `DISTINCT ON` su tutta la tabella). Percorso di migrazione se mai
servisse: cache Redis con TTL corto invalidata a fine import — solo se
misurato, non ora.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.detection_override import DetectionOverride
from app.models.transaction import Transaction
from app.services import analytics as analytics_service
from app.services import anomaly_calc, fx_rate_service, recurrence_calc
from app.services.analytics_calc import add_months_clamped
from app.services.merchant_extraction import extract_merchant

# Sotto questa soglia di storico disponibile nella finestra di analisi,
# nessun algoritmo qui puo' dire nulla di affidabile (un mese solo non ha
# baseline ne' puo' rivelare una cadenza) — `insufficient_data=True`, mai
# una lista vuota indistinguibile da "nessun abbonamento/nessuna anomalia".
_MIN_HISTORY_DAYS = 60
_ANOMALY_BASELINE_MONTHS = 12


@dataclass(frozen=True)
class MovementRow:
    transaction_id: uuid.UUID
    occurrence_date: date
    amount: Decimal | None
    currency: str
    merchant: str | None
    description_raw: str
    # Roll-up al padre (COALESCE(Category.parent_id, Transaction.category_id)
    # — stessa espressione di `analytics_service.by_category`, riusata
    # verbatim §2.1), MAI la foglia grezza: coerente con la baseline delle
    # anomalie per categoria.
    category_id: uuid.UUID | None


async def load_movements(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    direction: str,
    date_from: date,
    date_to: date,
    financial_account_id: uuid.UUID | None = None,
) -> list[MovementRow]:
    amount_filter = Transaction.amount < 0 if direction == "expense" else Transaction.amount > 0
    fx_rate = fx_rate_service.fx_rate_expr(Transaction.currency, Transaction.transaction_date, currency)
    converted_abs_amount = func.abs(Transaction.amount * fx_rate)
    group_category = func.coalesce(Category.parent_id, Transaction.category_id)
    query = (
        select(
            Transaction.id,
            Transaction.transaction_date,
            converted_abs_amount.label("amount"),
            Transaction.currency,
            Transaction.merchant,
            Transaction.description_raw,
            group_category.label("category_id"),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.transaction_type.notin_(analytics_service._EXCLUDED_FROM_CASH_FLOW),
            amount_filter,
            Transaction.transaction_date >= date_from,
            Transaction.transaction_date <= date_to,
        )
        .order_by(Transaction.transaction_date)
    )
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)

    rows = (await db.execute(query)).all()
    cents = Decimal("0.01")
    result = []
    for r in rows:
        amount = Decimal(r.amount).quantize(cents) if r.amount is not None else None
        result.append(
            MovementRow(
                transaction_id=r.id,
                occurrence_date=r.transaction_date,
                amount=amount,
                currency=r.currency,
                merchant=r.merchant,
                description_raw=r.description_raw,
                category_id=r.category_id,
            )
        )
    return result


async def _last_movement_date(
    db: AsyncSession, workspace_id: uuid.UUID, direction: str, financial_account_id: uuid.UUID | None = None
) -> date | None:
    """Ultima transazione REALE del workspace per quella direzione (mai
    limitata alla finestra di analisi) — il tetto che, applicato allo status
    "terminata"/"attiva" (§2.4), evita che un workspace il cui ultimo import
    e' vecchio segni OGNI serie come terminata (guardia mesi-fantasma)."""
    amount_filter = Transaction.amount < 0 if direction == "expense" else Transaction.amount > 0
    query = select(func.max(Transaction.transaction_date)).where(
        Transaction.workspace_id == workspace_id,
        Transaction.transaction_type.notin_(analytics_service._EXCLUDED_FROM_CASH_FLOW),
        amount_filter,
    )
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)
    return (await db.execute(query)).scalar_one_or_none()


def _label_for(movement: MovementRow) -> str:
    return movement.merchant or extract_merchant(movement.description_raw) or movement.description_raw[:60]


def _to_occurrences(movements: list[MovementRow], direction: str) -> list[recurrence_calc.Occurrence]:
    occurrences = []
    for m in movements:
        label = _label_for(m)
        token = recurrence_calc.series_token(m.merchant, m.description_raw)
        if token is None:
            continue
        series_key = recurrence_calc.series_key_for(direction, token)
        occurrences.append(
            recurrence_calc.Occurrence(
                transaction_id=m.transaction_id,
                occurrence_date=m.occurrence_date,
                series_key=series_key,
                label=label,
                amount=m.amount,
                currency=m.currency,
                category_id=m.category_id,
            )
        )
    return occurrences


async def _ignored_series_keys(db: AsyncSession, workspace_id: uuid.UUID) -> set[str]:
    result = await db.execute(
        select(DetectionOverride.series_key).where(
            DetectionOverride.workspace_id == workspace_id,
            DetectionOverride.override_type == "recurring_series",
            DetectionOverride.decision == "ignored",
        )
    )
    return {row[0] for row in result.all()}


async def _ignored_transaction_ids(db: AsyncSession, workspace_id: uuid.UUID) -> set[uuid.UUID]:
    result = await db.execute(
        select(DetectionOverride.transaction_id).where(
            DetectionOverride.workspace_id == workspace_id,
            DetectionOverride.override_type == "anomaly",
            DetectionOverride.decision == "ignored",
        )
    )
    return {row[0] for row in result.all()}


async def recurring_series(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    direction: str,
    as_of: date | None = None,
) -> dict:
    """Serie ricorrenti (§2.2-2.4, §2.7): NESSUN filtro conto ne'
    `date_from`/`date_to` — un solo mese non puo' mai rilevare ricorrenza, e
    il filtro conto spezzerebbe esattamente la serie che sposta carta (vedi
    docstring dell'endpoint in `app/api/v1/analytics.py`)."""
    resolved_as_of = as_of or date.today()
    window_from = add_months_clamped(resolved_as_of, -recurrence_calc.ANALYSIS_WINDOW_MONTHS)

    movements = await load_movements(db, workspace_id, currency, direction, window_from, resolved_as_of)
    data_coverage_end = await _last_movement_date(db, workspace_id, direction) or resolved_as_of

    occurrences = _to_occurrences(movements, direction)
    detected = recurrence_calc.detect_series(occurrences, resolved_as_of, data_coverage_end)

    ignored = await _ignored_series_keys(db, workspace_id)
    detected = [s for s in detected if s.series_key not in ignored]
    detected.sort(key=lambda s: (s.status != "active", -(s.monthly_equivalent or Decimal("0"))))

    category_ids = [s.category_id for s in detected if s.category_id is not None]
    categories = await analytics_service._category_names(db, category_ids)

    earliest = min((m.occurrence_date for m in movements), default=None)
    insufficient_data = earliest is None or (resolved_as_of - earliest).days < _MIN_HISTORY_DAYS

    monthly_total = sum(
        (s.monthly_equivalent for s in detected if s.status == "active" and s.monthly_equivalent is not None),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    has_unconverted_rows = any(m.amount is None for m in movements)

    items = []
    for s in detected:
        category = categories.get(s.category_id) if s.category_id is not None else None
        items.append(
            {
                "series_key": s.series_key,
                "label": s.label,
                "cadence": s.cadence,
                "status": s.status,
                "confidence": s.confidence,
                "occurrences_count": s.occurrences_count,
                "first_seen": s.first_seen,
                "last_seen": s.last_seen,
                "expected_next_date": s.expected_next_date,
                "expected_next_amount": s.expected_next_amount,
                "typical_amount": s.typical_amount,
                "monthly_equivalent": s.monthly_equivalent,
                "amount_is_variable": s.amount_is_variable,
                "price_change": (
                    {
                        "changed_at": s.price_change.changed_at,
                        "old_amount": s.price_change.old_amount,
                        "new_amount": s.price_change.new_amount,
                    }
                    if s.price_change is not None
                    else None
                ),
                "category_id": s.category_id,
                "category_name": category.name if category is not None else None,
                "multi_currency": s.multi_currency,
                "has_unconverted_rows": s.has_unconverted_rows,
                "occurrences": [
                    {"transaction_id": o.transaction_id, "transaction_date": o.occurrence_date, "amount": o.amount}
                    for o in s.occurrences
                ],
            }
        )

    return {
        "currency": currency,
        "direction": direction,
        "as_of": resolved_as_of,
        "analysis_window": {"date_from": window_from, "date_to": resolved_as_of},
        "monthly_total": monthly_total,
        "items": items,
        "insufficient_data": insufficient_data,
        "has_unconverted_rows": has_unconverted_rows,
    }


async def anomalies(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    direction: str,
    date_from: date,
    date_to: date,
    financial_account_id: uuid.UUID | None = None,
    limit: int = 10,
) -> dict:
    """Anomalie (§2.5): baseline SEMPRE a 12 mesi fino a `date_to` (mai il
    periodo richiesto — un mese solo non ha baseline), riportate solo per le
    transazioni dentro `date_from`/`date_to`. Le occorrenze di una serie
    ricorrente rilevata restano nel campione della categoria (non falsano la
    distribuzione) ma sono escluse dal test di categoria e valutate invece
    contro il livello della propria serie (`series_deviation`).

    NOTA (limite noto v1): la rilevazione delle serie qui e' ricalcolata
    sulla SOLA finestra baseline di 12 mesi (non sui 25 mesi di
    `recurring_series`) — piu' economico di una seconda query a 25 mesi ad
    ogni cambio di periodo delle anomalie, ma una cadenza `annual` (che
    richiede >12 mesi per 2 occorrenze) puo' non essere riconosciuta qui: in
    quel caso la transazione resta valutabile solo dal test di categoria.
    """
    baseline_from = add_months_clamped(date_to, -_ANOMALY_BASELINE_MONTHS)
    baseline_movements = await load_movements(
        db, workspace_id, currency, direction, baseline_from, date_to, financial_account_id
    )
    data_coverage_end = await _last_movement_date(db, workspace_id, direction, financial_account_id) or date_to

    occurrences = _to_occurrences(baseline_movements, direction)
    local_series = recurrence_calc.detect_series(occurrences, date_to, data_coverage_end)

    series_membership: dict[uuid.UUID, tuple[str, Decimal, date | None, int]] = {}
    for s in local_series:
        if s.typical_amount is None:
            continue
        price_change_at = s.price_change.changed_at if s.price_change is not None else None
        for o in s.occurrences:
            if o.amount is None:
                continue
            series_membership[o.transaction_id] = (s.series_key, s.typical_amount, price_change_at, s.occurrences_count)

    movement_by_id = {m.transaction_id: m for m in baseline_movements}

    category_samples = [
        anomaly_calc.CategorySample(
            transaction_id=m.transaction_id,
            occurrence_date=m.occurrence_date,
            amount=m.amount,
            category_id=m.category_id,
        )
        for m in baseline_movements
        if m.category_id is not None and m.amount is not None and m.transaction_id not in series_membership
    ]
    category_results = anomaly_calc.detect_category_outliers(category_samples)

    series_samples = [
        anomaly_calc.SeriesSample(
            transaction_id=txn_id,
            occurrence_date=movement_by_id[txn_id].occurrence_date,
            amount=movement_by_id[txn_id].amount,
            category_id=movement_by_id[txn_id].category_id,
            series_key=series_key,
            level=level,
            sample_size=sample_size,
            price_change_at=price_change_at,
        )
        for txn_id, (series_key, level, price_change_at, sample_size) in series_membership.items()
        if movement_by_id[txn_id].amount is not None
    ]
    series_results = anomaly_calc.detect_series_deviations(series_samples)

    combined = category_results + series_results
    combined = [r for r in combined if date_from <= r.occurrence_date <= date_to]

    ignored = await _ignored_transaction_ids(db, workspace_id)
    combined = [r for r in combined if r.transaction_id not in ignored]
    combined.sort(key=lambda r: abs(r.deviation_amount), reverse=True)
    combined = combined[: max(1, min(limit, 50))]

    category_ids = [r.category_id for r in combined if r.category_id is not None]
    categories = await analytics_service._category_names(db, category_ids)

    earliest = min((m.occurrence_date for m in baseline_movements), default=None)
    insufficient_data = earliest is None or (date_to - earliest).days < _MIN_HISTORY_DAYS
    has_unconverted_rows = any(
        m.amount is None for m in baseline_movements if date_from <= m.occurrence_date <= date_to
    )

    items = []
    for r in combined:
        movement = movement_by_id[r.transaction_id]
        category = categories.get(r.category_id) if r.category_id is not None else None
        items.append(
            {
                "transaction_id": r.transaction_id,
                "transaction_date": r.occurrence_date,
                "label": _label_for(movement),
                "amount": r.amount,
                "currency": currency,
                "anomaly_type": r.anomaly_type,
                "category_id": r.category_id,
                "category_name": category.name if category is not None else None,
                "baseline_amount": r.baseline_amount,
                "deviation_amount": r.deviation_amount,
                "deviation_pct": r.deviation_pct,
                "robust_score": r.robust_score,
                "sample_size": r.sample_size,
                "series_key": r.series_key,
            }
        )

    return {
        "currency": currency,
        "direction": direction,
        "period": {"date_from": date_from, "date_to": date_to},
        "baseline": {"date_from": baseline_from, "date_to": date_to},
        "items": items,
        "insufficient_data": insufficient_data,
        "has_unconverted_rows": has_unconverted_rows,
    }


async def upsert_override(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    override_type: str,
    decision: str,
    series_key: str | None,
    transaction_id: uuid.UUID | None,
) -> DetectionOverride:
    """Upsert idempotente (§2.7: `POST .../detection-overrides -> 201`) —
    stesso pattern SELECT-poi-INSERT/UPDATE di `fx_rate_service.upsert_rate`
    (nessun precedente `ON CONFLICT` nel repo): un secondo POST sullo stesso
    target (stesso `workspace_id` + `series_key`/`transaction_id` a seconda
    di `override_type`, i due indici UNIQUE PARZIALI della migration 0035)
    aggiorna `decision`/`created_by_user_id`/`created_at` invece di fallire
    o duplicare."""
    query = select(DetectionOverride).where(
        DetectionOverride.workspace_id == workspace_id,
        DetectionOverride.override_type == override_type,
    )
    if override_type == "recurring_series":
        query = query.where(DetectionOverride.series_key == series_key)
    else:
        query = query.where(DetectionOverride.transaction_id == transaction_id)

    existing = (await db.execute(query)).scalar_one_or_none()
    if existing is not None:
        existing.decision = decision
        existing.created_by_user_id = user_id
        existing.created_at = func.now()
        # flush+refresh PRIMA del commit (RLS gotcha noto: `SET LOCAL
        # app.current_user_id` scade al commit — un `db.refresh()` fatto
        # DOPO il commit farebbe una SELECT su `detection_overrides` senza
        # piu' identita' RLS, fallendo con "invalid input syntax for type
        # uuid: ''"; qui serve anche a risolvere `created_at = func.now()`
        # al valore reale scritto da Postgres invece dell'espressione SQL
        # non valutata, stessa correzione gia' applicata in
        # `upsert_manual_asset_price`/`position_service.py`).
        await db.flush()
        await db.refresh(existing)
        await db.commit()
        return existing

    override = DetectionOverride(
        workspace_id=workspace_id,
        override_type=override_type,
        series_key=series_key,
        transaction_id=transaction_id,
        decision=decision,
        created_by_user_id=user_id,
    )
    db.add(override)
    await db.flush()
    await db.refresh(override)
    await db.commit()
    return override


async def delete_override(db: AsyncSession, workspace_id: uuid.UUID, override_id: uuid.UUID) -> bool:
    """`True` se una riga del workspace corrente e' stata cancellata — il
    chiamante (endpoint DELETE) traduce l'assenza in 404, doppio controllo
    ownership applicativo oltre alla RLS (CLAUDE.md: mai fidarsi della sola
    RLS ne' del solo check applicativo)."""
    override = await db.get(DetectionOverride, override_id)
    if override is None or override.workspace_id != workspace_id:
        return False
    await db.delete(override)
    await db.commit()
    return True

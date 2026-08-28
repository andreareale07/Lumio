import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import (
    GRANULARITIES,
    AccountBalanceOut,
    BalanceHistoryOut,
    BalanceHistoryPointOut,
    BalancesOut,
    CashFlowOut,
    CashFlowPointOut,
    CategoryBreakdownItemOut,
    CategoryBreakdownOut,
    CategoryTrendOut,
    CategoryTrendSeriesOut,
    MerchantBreakdownItemOut,
    MerchantBreakdownOut,
    PeriodOut,
    SummaryOut,
)
from app.schemas.detection import (
    AnomalyItemOut,
    AnomalyListOut,
    DetectionOverrideIn,
    DetectionOverrideOut,
    RecurringOccurrenceOut,
    RecurringPriceChangeOut,
    RecurringSeriesItemOut,
    RecurringSeriesListOut,
)
from app.schemas.portfolio_analytics import NetWorthHistoryOut, NetWorthSnapshotPointOut
from app.services import analytics as analytics_service
from app.services import detection as detection_service
from app.services import portfolio_analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])

_DIRECTIONS = ("expense", "income")


def _default_period() -> tuple[date, date]:
    """"Questo mese" (SPEC_FE §12.2), il primo preset del filtro periodo,
    usato quando il chiamante non specifica un range esplicito."""
    today = date.today()
    return today.replace(day=1), today


def _resolve_period(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    if date_from is None or date_to is None:
        default_from, default_to = _default_period()
        date_from = date_from or default_from
        date_to = date_to or default_to
    if date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from deve precedere date_to")
    return date_from, date_to


def _validate_granularity(granularity: str) -> str:
    if granularity not in GRANULARITIES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"granularity deve essere una tra: {', '.join(GRANULARITIES)}",
        )
    return granularity


@router.get("/summary", response_model=SummaryOut)
async def get_summary(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> SummaryOut:
    date_from, date_to = _resolve_period(date_from, date_to)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    result = await analytics_service.summary(db, workspace_id, resolved_currency, date_from, date_to)
    return SummaryOut(
        currency=result["currency"],
        period=PeriodOut(**result["period"]),
        comparison_period=PeriodOut(**result["comparison_period"]),
        liquidity=result["liquidity"],
        debt=result["debt"],
        investments=result["investments"],
        net_worth=result["net_worth"],
        has_investments=result["has_investments"],
        income=result["income"],
        expenses=result["expenses"],
        net_cash_flow=result["net_cash_flow"],
        previous_income=result["previous_income"],
        previous_expenses=result["previous_expenses"],
        previous_net_cash_flow=result["previous_net_cash_flow"],
        has_unconverted_rows=result["has_unconverted_rows"],
    )


@router.get("/balances", response_model=BalancesOut)
async def get_balances(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    currency: str | None = None,
    as_of: date | None = None,
) -> BalancesOut:
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_as_of = as_of or date.today()
    balances = await analytics_service.account_balances(
        db, workspace_id, resolved_currency, resolved_as_of
    )
    return BalancesOut(
        currency=resolved_currency,
        as_of=resolved_as_of,
        accounts=[
            AccountBalanceOut(
                financial_account_id=a.financial_account_id,
                name=a.name,
                account_type=a.account_type,
                balance=a.balance,
            )
            for a in balances.accounts
        ],
        liquidity_total=balances.liquidity_total,
        debt_total=balances.debt_total,
        investment_total=balances.investment_total,
        has_investments=balances.has_investments,
        has_unconverted_rows=balances.has_unconverted_rows,
    )


@router.get("/balance-history", response_model=BalanceHistoryOut)
async def get_balance_history(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: str = "month",
    currency: str | None = None,
    financial_account_id: uuid.UUID | None = None,
) -> BalanceHistoryOut:
    date_from, date_to = _resolve_period(date_from, date_to)
    granularity = _validate_granularity(granularity)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    points = await analytics_service.balance_history(
        db, workspace_id, resolved_currency, granularity, date_from, date_to, financial_account_id
    )
    return BalanceHistoryOut(
        currency=resolved_currency,
        granularity=granularity,
        period=PeriodOut(date_from=date_from, date_to=date_to),
        points=[BalanceHistoryPointOut(**p) for p in points],
    )


@router.get("/cash-flow", response_model=CashFlowOut)
async def get_cash_flow(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: str = "month",
    currency: str | None = None,
    financial_account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
) -> CashFlowOut:
    date_from, date_to = _resolve_period(date_from, date_to)
    granularity = _validate_granularity(granularity)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    points = await analytics_service.cash_flow(
        db, workspace_id, resolved_currency, granularity, date_from, date_to, financial_account_id, category_id
    )
    return CashFlowOut(
        currency=resolved_currency,
        granularity=granularity,
        period=PeriodOut(date_from=date_from, date_to=date_to),
        points=[CashFlowPointOut(**p) for p in points],
    )


@router.get("/by-category", response_model=CategoryBreakdownOut)
async def get_by_category(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    direction: str = Query(default="expense", pattern="^(" + "|".join(_DIRECTIONS) + ")$"),
    currency: str | None = None,
    financial_account_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
) -> CategoryBreakdownOut:
    date_from, date_to = _resolve_period(date_from, date_to)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    items = await analytics_service.by_category(
        db, workspace_id, resolved_currency, direction, date_from, date_to, financial_account_id, parent_id
    )
    return CategoryBreakdownOut(
        currency=resolved_currency,
        direction=direction,
        period=PeriodOut(date_from=date_from, date_to=date_to),
        items=[CategoryBreakdownItemOut(**i) for i in items],
    )


@router.get("/category-trend", response_model=CategoryTrendOut)
async def get_category_trend(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: str = "month",
    direction: str = Query(default="expense", pattern="^(" + "|".join(_DIRECTIONS) + ")$"),
    currency: str | None = None,
    financial_account_id: uuid.UUID | None = None,
    parent_id: uuid.UUID | None = None,
) -> CategoryTrendOut:
    """Matrice bucket x categoria per le sparkline/scostamenti della
    gerarchia categorie di Spese/Entrate (redesign FETTA 1) — vedi il
    docstring di `analytics_service.category_trend` per il perche' di
    un'unica query invece di N chiamate a `/cash-flow`."""
    date_from, date_to = _resolve_period(date_from, date_to)
    granularity = _validate_granularity(granularity)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    result = await analytics_service.category_trend(
        db,
        workspace_id,
        resolved_currency,
        direction,
        granularity,
        date_from,
        date_to,
        financial_account_id,
        parent_id,
    )
    return CategoryTrendOut(
        currency=resolved_currency,
        direction=direction,
        granularity=granularity,
        period=PeriodOut(date_from=date_from, date_to=date_to),
        buckets=result["buckets"],
        series=[CategoryTrendSeriesOut(**s) for s in result["series"]],
    )


@router.get("/net-worth-history", response_model=NetWorthHistoryOut)
async def get_net_worth_history(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
    granularity: str | None = None,
) -> NetWorthHistoryOut:
    """Storico patrimonio (SPEC §31) — legge SEMPRE dagli snapshot gia'
    scritti (`net_worth_snapshots`, cron/trigger manuale/backfill FETTA 3),
    mai ricalcolato da zero: a differenza di `/balance-history` (M08,
    ricostruito a ritroso dalle sole transazioni), qui il patrimonio include
    gli investimenti a valore di mercato, che non e' derivabile dalle sole
    transazioni bancarie (DoD M09).

    `granularity` (FETTA 3, storico patrimonio ricostruito): `None` (default)
    = righe giornaliere grezze, comportamento invariato di prima di questa
    fetta. Con lo storico ricostruito (backfill giornaliero su anni, non
    solo cron da oggi in poi) una `trendWindow` larga produrrebbe migliaia
    di punti — passare una granularita' esplicita downsampla server-side
    (un punto per bucket, l'ultimo disponibile)."""
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_to = date_to or date.today()
    resolved_from = date_from or (resolved_to - timedelta(days=365))
    if granularity is not None:
        granularity = _validate_granularity(granularity)
        snapshots = await portfolio_analytics.list_net_worth_snapshots_downsampled(
            db, workspace_id, granularity, resolved_from, resolved_to
        )
    else:
        snapshots = await portfolio_analytics.list_net_worth_snapshots(db, workspace_id, resolved_from, resolved_to)

    matching = [s for s in snapshots if s.currency == resolved_currency]
    return NetWorthHistoryOut(
        currency=resolved_currency,
        points=[
            NetWorthSnapshotPointOut(
                snapshot_date=s.snapshot_date,
                liquidity=s.liquidity,
                debt=s.debt,
                investments=s.investments,
                net_worth=s.net_worth,
            )
            for s in matching
        ],
        # Bug latente pre-esistente reso onesto (FETTA 3): scartare in
        # silenzio le righe con valuta diversa svuotava il grafico dopo un
        # cambio di `base_currency` senza alcuna spiegazione in UI — ora la
        # pagina puo' dire "ricostruisci lo storico" invece di mostrare un
        # grafico vuoto.
        has_mixed_currency=len(matching) < len(snapshots),
    )


@router.get("/by-merchant", response_model=MerchantBreakdownOut)
async def get_by_merchant(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    direction: str = Query(default="expense", pattern="^(" + "|".join(_DIRECTIONS) + ")$"),
    currency: str | None = None,
    financial_account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
) -> MerchantBreakdownOut:
    date_from, date_to = _resolve_period(date_from, date_to)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    items = await analytics_service.by_merchant(
        db,
        workspace_id,
        resolved_currency,
        direction,
        date_from,
        date_to,
        financial_account_id,
        category_id,
    )
    return MerchantBreakdownOut(
        currency=resolved_currency,
        direction=direction,
        period=PeriodOut(date_from=date_from, date_to=date_to),
        items=[MerchantBreakdownItemOut(**i) for i in items],
    )


# --- Ricorrenze e anomalie (piano synchronous-chasing-pike.md, FETTA 2) ----
# Due algoritmi puri e deterministici (mai AI-dipendenti — l'app deve
# funzionare al 100% con AI_PROVIDER=none, CLAUDE.md), calcolati on-the-fly
# a ogni richiesta (vedi docstring di modulo di `app/services/detection.py`
# sul perche' nessuna tabella derivata).


@router.get("/recurring", response_model=RecurringSeriesListOut)
async def get_recurring(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    direction: str = Query(default="expense", pattern="^(" + "|".join(_DIRECTIONS) + ")$"),
    currency: str | None = None,
    as_of: date | None = None,
) -> RecurringSeriesListOut:
    """Serie ricorrenti rilevate (abbonamenti, stipendi, affitti...) — SENZA
    `date_from`/`date_to` ne' `financial_account_id`, deliberatamente: un
    solo mese non puo' mai rilevare una ricorrenza, e un filtro conto
    spezzerebbe esattamente la serie che si sposta da una carta all'altra
    (la chiave di serie non include `financial_account_id`/`currency` per
    costruzione, vedi `recurrence_calc.series_key_for`). La risposta include
    `analysis_window` cosi' la pagina puo' dichiarare il periodo realmente
    usato (25 mesi indietro da `as_of`)."""
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    result = await detection_service.recurring_series(
        db, workspace_id, resolved_currency, direction, as_of
    )
    return RecurringSeriesListOut(
        currency=result["currency"],
        direction=result["direction"],
        as_of=result["as_of"],
        analysis_window=PeriodOut(**result["analysis_window"]),
        monthly_total=result["monthly_total"],
        items=[
            RecurringSeriesItemOut(
                **{
                    **i,
                    "price_change": RecurringPriceChangeOut(**i["price_change"]) if i["price_change"] else None,
                    "occurrences": [RecurringOccurrenceOut(**o) for o in i["occurrences"]],
                }
            )
            for i in result["items"]
        ],
        insufficient_data=result["insufficient_data"],
        has_unconverted_rows=result["has_unconverted_rows"],
    )


@router.get("/anomalies", response_model=AnomalyListOut)
async def get_anomalies(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    direction: str = Query(default="expense", pattern="^(" + "|".join(_DIRECTIONS) + ")$"),
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
    financial_account_id: uuid.UUID | None = None,
    limit: int = Query(default=10, ge=1, le=50),
) -> AnomalyListOut:
    """Transazioni anomale nel periodo, rispetto a una baseline SEMPRE di 12
    mesi fino a `date_to` (mai il periodo richiesto — un mese solo non ha
    baseline, vedi `baseline` nella risposta). Due tipi distinti
    (`category_outlier`/`series_deviation`, §2.5 del piano): una transazione
    membro di una serie ricorrente rilevata non puo' mai comparire come
    `category_outlier` (distorcerebbe la lettura — 49€ e' ordinario dentro
    "Abbonamenti" se quello e' il livello della serie), viene invece
    valutata contro il livello della propria serie."""
    date_from, date_to = _resolve_period(date_from, date_to)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    result = await detection_service.anomalies(
        db, workspace_id, resolved_currency, direction, date_from, date_to, financial_account_id, limit
    )
    return AnomalyListOut(
        currency=result["currency"],
        direction=result["direction"],
        period=PeriodOut(**result["period"]),
        baseline=PeriodOut(**result["baseline"]),
        items=[AnomalyItemOut(**i) for i in result["items"]],
        insufficient_data=result["insufficient_data"],
        has_unconverted_rows=result["has_unconverted_rows"],
    )


@router.post("/detection-overrides", response_model=DetectionOverrideOut, status_code=status.HTTP_201_CREATED)
async def create_detection_override(
    payload: DetectionOverrideIn,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DetectionOverrideOut:
    """Upsert idempotente (§2.8 del piano — CLAUDE.md: "le correzioni
    manuali hanno sempre priorita' sull'AI", qui applicato a un algoritmo
    deterministico invece che a un provider AI, stesso principio: il
    fallimento dominante e' un falso positivo che l'utente deve poter
    silenziare). Esattamente uno tra `series_key`/`transaction_id` deve
    essere valorizzato, coerente con `override_type` (CHECK nel DB, non
    solo qui)."""
    if payload.override_type == "recurring_series" and not payload.series_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "series_key richiesto per override_type=recurring_series")
    if payload.override_type == "anomaly" and payload.transaction_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "transaction_id richiesto per override_type=anomaly")
    override = await detection_service.upsert_override(
        db,
        workspace_id,
        user.id,
        payload.override_type,
        payload.decision,
        payload.series_key,
        payload.transaction_id,
    )
    return DetectionOverrideOut(
        id=override.id,
        workspace_id=override.workspace_id,
        override_type=override.override_type,
        series_key=override.series_key,
        transaction_id=override.transaction_id,
        decision=override.decision,
        created_at=override.created_at,
    )


@router.delete("/detection-overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_detection_override(
    override_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """"Annulla" (undo del dismiss): rimuove l'override, il segnale
    ricompare alla richiesta successiva (nessuno stato "annullato" separato
    da mantenere — la cancellazione della riga E' l'annullamento)."""
    deleted = await detection_service.delete_override(db, workspace_id, override_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Override not found")

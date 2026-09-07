import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.core.config import get_settings
from app.db.session import get_db
from app.models.financial_account import FinancialAccount
from app.models.portfolio import Portfolio
from app.models.portfolio_account import PortfolioAccount
from app.models.user import User
from app.schemas.job_runs import JobRunOut
from app.schemas.portfolio_analytics import (
    AllocationItemOut,
    PortfolioAllocationOut,
    PortfolioPerformanceOut,
    PortfolioPositionsOut,
    PortfolioSnapshotPointOut,
    PortfolioSummaryItemOut,
    PortfolioSummaryListOut,
    PortfolioValuationOut,
    PositionValuationOut,
)
from app.schemas.portfolios import (
    PortfolioAccountCreate,
    PortfolioAccountOut,
    PortfolioCreate,
    PortfolioOut,
    PortfolioUpdate,
    SnapshotBackfillRequest,
    SnapshotBackfillTriggered,
    SnapshotRebuildTriggered,
)
from app.services import analytics as analytics_service
from app.services import job_events, portfolio_analytics
from app.services.job_run_tracker import get_latest_run
from app.services.portfolio_scope import get_portfolio_or_404, resolve_account_ids
from app.worker.jobs.snapshot_backfill import JOB_KIND as SNAPSHOT_BACKFILL_JOB_KIND
from app.worker.jobs.snapshot_backfill import NAMESPACE as SNAPSHOT_BACKFILL_NAMESPACE
from app.worker.queue import enqueue_snapshot_backfill, enqueue_snapshot_rebuild

router = APIRouter(prefix="/portfolios", tags=["portfolio"])


# --- Analytics (SPEC §37): valore, allocation, performance -----------------
# Path a due segmenti ("/analytics/..."), non "/{parola}" a un segmento: una
# route statica a un segmento solo collinerebbe con "/{portfolio_id}" nello
# stesso router (Starlette la farebbe combaciare per prima e proverebbe a
# interpretare "valuation" come UUID, 422 — mai raggiungendo l'handler
# giusto). Stesso schema a due segmenti gia' usato da "/snapshots/rebuild".


@router.get("/analytics/valuation", response_model=PortfolioValuationOut)
async def get_portfolio_valuation(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    portfolio_id: uuid.UUID | None = None,
    unassigned: bool = False,
    as_of: date | None = None,
    currency: str | None = None,
) -> PortfolioValuationOut:
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_as_of = as_of or date.today()
    account_ids = await resolve_account_ids(db, workspace_id, portfolio_id, unassigned)
    valuation = await portfolio_analytics.compute_valuation(
        db, workspace_id, account_ids, resolved_as_of, resolved_currency
    )
    return PortfolioValuationOut(
        currency=valuation.currency,
        as_of=resolved_as_of,
        market_value=valuation.market_value,
        cost_basis=valuation.cost_basis,
        unrealized_pl=valuation.unrealized_pl,
        realized_pl=valuation.realized_pl,
        has_market_data=valuation.has_market_data,
        has_holdings=valuation.has_holdings,
        has_missing_fx_rate=valuation.has_missing_fx_rate,
    )


@router.get("/analytics/allocation", response_model=PortfolioAllocationOut)
async def get_portfolio_allocation(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    portfolio_id: uuid.UUID | None = None,
    unassigned: bool = False,
    as_of: date | None = None,
    currency: str | None = None,
) -> PortfolioAllocationOut:
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_as_of = as_of or date.today()
    account_ids = await resolve_account_ids(db, workspace_id, portfolio_id, unassigned)
    allocation = await portfolio_analytics.compute_allocation(
        db, workspace_id, account_ids, resolved_as_of, resolved_currency
    )

    def to_items(items):
        return [AllocationItemOut(key=i.key, label=i.label, value=i.value, share=i.share) for i in items]

    return PortfolioAllocationOut(
        currency=allocation.currency,
        as_of=resolved_as_of,
        has_market_data=allocation.has_market_data,
        has_missing_fx_rate=allocation.has_missing_fx_rate,
        by_asset_type=to_items(allocation.by_asset_type),
        by_asset=to_items(allocation.by_asset),
        by_account=to_items(allocation.by_account),
        by_currency=to_items(allocation.by_currency),
        by_strategy=to_items(allocation.by_strategy),
    )


@router.get("/analytics/performance", response_model=PortfolioPerformanceOut)
async def get_portfolio_performance(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    portfolio_id: uuid.UUID | None = None,
    unassigned: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> PortfolioPerformanceOut:
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_to = date_to or date.today()
    resolved_from = date_from or (resolved_to - timedelta(days=365))
    account_ids = await resolve_account_ids(db, workspace_id, portfolio_id, unassigned)
    series = await portfolio_analytics.compute_historical_series(
        db, workspace_id, account_ids, resolved_from, resolved_to, resolved_currency
    )
    return PortfolioPerformanceOut(
        currency=resolved_currency,
        points=[
            PortfolioSnapshotPointOut(
                snapshot_date=checkpoint,
                market_value=valuation.market_value,
                cost_basis=valuation.cost_basis,
                unrealized_pl=valuation.unrealized_pl,
                realized_pl=valuation.realized_pl,
                has_market_data=valuation.has_market_data,
            )
            for checkpoint, valuation in series
        ],
    )


@router.get("/analytics/summary", response_model=PortfolioSummaryListOut)
async def get_portfolio_summaries(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    as_of: date | None = None,
    currency: str | None = None,
) -> PortfolioSummaryListOut:
    """Riepilogo di ogni `Portfolio` del workspace in una sola risposta —
    usato dalla Panoramica Investimenti (redesign) per la lista dei
    portfolio senza fare N chiamate separate lato client. Non include lo
    pseudo-gruppo "Asset senza portfolio": quello si valorizza con
    `GET /analytics/valuation?unassigned=true`, gia' esistente."""
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_as_of = as_of or date.today()
    summaries = await portfolio_analytics.list_portfolio_summaries(
        db, workspace_id, resolved_as_of, resolved_currency
    )
    return PortfolioSummaryListOut(
        as_of=resolved_as_of,
        items=[
            PortfolioSummaryItemOut(
                portfolio_id=s.portfolio_id,
                name=s.name,
                account_count=s.account_count,
                currency=s.currency,
                market_value=s.market_value,
                cost_basis=s.cost_basis,
                unrealized_pl=s.unrealized_pl,
                has_market_data=s.has_market_data,
                has_holdings=s.has_holdings,
            )
            for s in summaries
        ],
    )


@router.get("/analytics/positions", response_model=PortfolioPositionsOut)
async def get_portfolio_positions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    portfolio_id: uuid.UUID | None = None,
    unassigned: bool = False,
    as_of: date | None = None,
    currency: str | None = None,
    include_closed: bool = False,
    realized_only: bool = Query(default=False),
    asset_id: uuid.UUID | None = Query(default=None),
    financial_account_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PortfolioPositionsOut:
    """Valore attuale e rendimento PER SINGOLA posizione (redesign
    Investimenti, tabella Posizioni) — a differenza del calcolo client-side
    precedente (mai possibile senza `fx_rate_service`), qui la conversione
    valuta e' sempre corretta anche quando prezzo e posizione sono in
    valute diverse. Riusa `list_position_valuations`, gia' scritta e
    testata per l'export Google Sheets.

    `realized_only`/`asset_id`/`financial_account_id`/`limit`/`offset` sono
    tutti opzionali e filtrano/paginano SOPRA il risultato (vista "Utile
    realizzato", FETTA successiva a FETTA 2 fiscale) — quando `limit` e'
    assente il comportamento resta identico a prima (nessuna paginazione,
    `PortfolioDetailPage` non passa questi parametri). `realized_only`
    forza `include_closed=True` internamente: una posizione chiusa con
    P&L realizzato residuo non deve sparire dalla lista."""
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_as_of = as_of or date.today()
    account_ids = await resolve_account_ids(db, workspace_id, portfolio_id, unassigned)
    result = await portfolio_analytics.list_position_valuations(
        db, workspace_id, account_ids, resolved_as_of, resolved_currency, include_closed or realized_only
    )
    page, total = portfolio_analytics.paginate_position_valuations(
        result.items,
        asset_id=asset_id,
        financial_account_id=financial_account_id,
        realized_only=realized_only,
        limit=limit,
        offset=offset,
    )
    return PortfolioPositionsOut(
        currency=resolved_currency,
        as_of=resolved_as_of,
        has_market_data=result.has_market_data,
        has_missing_fx_rate=result.has_missing_fx_rate,
        total=total,
        positions=[
            PositionValuationOut(
                position_id=p.position_id,
                asset_id=p.asset_id,
                asset_label=p.asset_label,
                financial_account_id=p.financial_account_id,
                account_label=p.account_label,
                quantity=p.quantity,
                average_cost=p.average_cost,
                currency=p.currency,
                currency_native=p.currency_native,
                cost_basis=p.cost_basis,
                market_value=p.market_value,
                unrealized_pl=p.unrealized_pl,
                realized_pl=p.realized_pl,
                has_market_data=p.has_market_data,
            )
            for p in page
        ],
    )


@router.post("", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: PortfolioCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Portfolio:
    portfolio = Portfolio(workspace_id=workspace_id, **payload.model_dump())
    db.add(portfolio)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Portfolio name already used") from exc
    return portfolio


@router.get("", response_model=list[PortfolioOut])
async def list_portfolios(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[Portfolio]:
    result = await db.execute(
        select(Portfolio).where(Portfolio.workspace_id == workspace_id).order_by(Portfolio.name)
    )
    return list(result.scalars().all())


@router.get("/{portfolio_id}", response_model=PortfolioOut)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Portfolio:
    return await get_portfolio_or_404(db, workspace_id, portfolio_id)


@router.patch("/{portfolio_id}", response_model=PortfolioOut)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    payload: PortfolioUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Portfolio:
    portfolio = await get_portfolio_or_404(db, workspace_id, portfolio_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(portfolio, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Portfolio name already used") from exc
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    portfolio = await get_portfolio_or_404(db, workspace_id, portfolio_id)
    await db.delete(portfolio)
    await db.commit()


# --- conti associati (SPEC §36: portfolio aggregabili su piu' conti) -----------


@router.get("/{portfolio_id}/accounts", response_model=list[PortfolioAccountOut])
async def list_portfolio_accounts(
    portfolio_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[PortfolioAccount]:
    await get_portfolio_or_404(db, workspace_id, portfolio_id)
    result = await db.execute(
        select(PortfolioAccount)
        .where(PortfolioAccount.workspace_id == workspace_id, PortfolioAccount.portfolio_id == portfolio_id)
        .order_by(PortfolioAccount.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/{portfolio_id}/accounts", response_model=PortfolioAccountOut, status_code=status.HTTP_201_CREATED
)
async def add_portfolio_account(
    portfolio_id: uuid.UUID,
    payload: PortfolioAccountCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> PortfolioAccount:
    await get_portfolio_or_404(db, workspace_id, portfolio_id)
    account = await db.get(FinancialAccount, payload.financial_account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid financial_account_id")

    link = PortfolioAccount(
        workspace_id=workspace_id,
        portfolio_id=portfolio_id,
        financial_account_id=payload.financial_account_id,
    )
    db.add(link)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account already in this portfolio") from exc
    return link


@router.delete("/{portfolio_id}/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_portfolio_account(
    portfolio_id: uuid.UUID,
    account_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_portfolio_or_404(db, workspace_id, portfolio_id)
    result = await db.execute(
        select(PortfolioAccount).where(
            PortfolioAccount.workspace_id == workspace_id,
            PortfolioAccount.portfolio_id == portfolio_id,
            PortfolioAccount.financial_account_id == account_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not linked to this portfolio")
    await db.delete(link)
    await db.commit()


# --- Snapshot (SPEC §31/§37, DoD M09) --------------------------------------


@router.post(
    "/snapshots/rebuild", response_model=SnapshotRebuildTriggered, status_code=status.HTTP_202_ACCEPTED
)
async def trigger_snapshot_rebuild(
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> SnapshotRebuildTriggered:
    """Ricalcolo manuale dello snapshot del giorno (in aggiunta al cron
    giornaliero, vedi `app/worker/main.py`) — utile subito dopo aver
    configurato un provider o corretto una posizione, senza aspettare la
    prossima esecuzione schedulata. Job async, stesso principio (e stesso
    bugfix anti-doppio-click via `job_runs`) di `trigger_market_data_refresh`."""
    current = await get_latest_run(db, workspace_id, "snapshot_rebuild")
    if current is not None and current.status == "running":
        return SnapshotRebuildTriggered(job_id=current.job_id or "")
    job_id = await enqueue_snapshot_rebuild(workspace_id, user.id)
    return SnapshotRebuildTriggered(job_id=job_id)


@router.get("/snapshots/status", response_model=JobRunOut | None)
async def get_snapshot_rebuild_status(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> JobRunOut | None:
    """Stato persistente dell'ultimo ricalcolo (manuale o cron) — stesso
    principio di `get_market_data_refresh_status`. `null` se non e' mai
    stato eseguito."""
    run = await get_latest_run(db, workspace_id, "snapshot_rebuild")
    return JobRunOut.model_validate(run) if run else None


# --- Storico patrimonio ricostruito (FETTA 3) -------------------------------
# Endpoint NUOVO, non un flag su "/snapshots/rebuild": i due job scrivono
# righe `job_runs` diverse (`job_kind` diversi), quindi guardia anti-
# doppio-click e stato devono essere per-kind comunque; la semantica
# differisce (secondi vs minuti — nessun `setTimeout(refetch)` ha senso
# qui); e la terna endpoint/status/events rispecchia esattamente
# `/classification/reclassify*` (vedi `api/v1/classification.py`).


@router.post(
    "/snapshots/backfill", response_model=SnapshotBackfillTriggered, status_code=status.HTTP_202_ACCEPTED
)
async def trigger_snapshot_backfill(
    payload: SnapshotBackfillRequest | None = None,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> SnapshotBackfillTriggered:
    """Ricostruzione manuale dell'INTERO storico patrimonio disponibile (o
    da `payload.date_from` se specificato) — a differenza di
    "Ricalcola adesso" (`trigger_snapshot_rebuild`, solo lo snapshot di
    OGGI), questo job puo' impiegare minuti/ore (fase prezzi storici
    inclusa). Stesso principio anti-doppio-click via `job_runs` di
    `trigger_snapshot_rebuild`/`trigger_reclassification`: se e' gia'
    'running', ritorna lo stesso job_id invece di accodarne un secondo."""
    current = await get_latest_run(db, workspace_id, SNAPSHOT_BACKFILL_JOB_KIND)
    if current is not None and current.status == "running":
        return SnapshotBackfillTriggered(job_id=current.job_id or "")
    date_from = payload.date_from if payload is not None else None
    job_id = await enqueue_snapshot_backfill(workspace_id, user.id, date_from=date_from)
    return SnapshotBackfillTriggered(job_id=job_id)


@router.get("/snapshots/backfill/status", response_model=JobRunOut | None)
async def get_snapshot_backfill_status(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> JobRunOut | None:
    """Stato persistente dell'ultimo backfill (manuale o automatico a fine
    import) — `null` se non e' mai stato eseguito."""
    run = await get_latest_run(db, workspace_id, SNAPSHOT_BACKFILL_JOB_KIND)
    return JobRunOut.model_validate(run) if run else None


@router.get("/snapshots/backfill/events")
async def stream_snapshot_backfill_events(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> StreamingResponse:
    """Mirror di `stream_reclassification_events`
    (`api/v1/classification.py`), `topic_id=workspace_id` (un solo backfill
    alla volta per workspace). A differenza di quell'endpoint, passa
    esplicitamente il timeout proprio del job (`snapshot_backfill_job_timeout_
    seconds`, fino a 3 ore) invece del default `import_job_timeout_seconds`
    di `job_events.stream` — un job che puo' durare ore chiuderebbe
    prematuramente lo stream SSE altrimenti."""
    return StreamingResponse(
        job_events.stream(
            workspace_id,
            namespace=SNAPSHOT_BACKFILL_NAMESPACE,
            timeout_seconds=get_settings().snapshot_backfill_job_timeout_seconds,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

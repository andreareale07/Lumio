import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
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
    PortfolioSnapshotPointOut,
    PortfolioValuationOut,
)
from app.schemas.portfolios import (
    PortfolioAccountCreate,
    PortfolioAccountOut,
    PortfolioCreate,
    PortfolioOut,
    PortfolioUpdate,
    SnapshotRebuildTriggered,
)
from app.services import analytics as analytics_service
from app.services import portfolio_analytics
from app.services.job_run_tracker import get_latest_run
from app.worker.queue import enqueue_snapshot_rebuild

router = APIRouter(prefix="/portfolios", tags=["portfolio"])


async def _get_portfolio_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, portfolio_id: uuid.UUID
) -> Portfolio:
    portfolio = await db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found")
    return portfolio


async def _resolve_account_ids(
    db: AsyncSession, workspace_id: uuid.UUID, portfolio_id: uuid.UUID | None
) -> set[uuid.UUID] | None:
    """`portfolio_id=None` risolve nella vista implicita "tutti i conti"
    (SPEC §36) — `None` propagato a `compute_valuation`/`compute_allocation`
    significa "nessun filtro", non "nessun conto"."""
    if portfolio_id is None:
        return None
    await _get_portfolio_or_404(db, workspace_id, portfolio_id)
    links = (
        await db.execute(
            select(PortfolioAccount).where(
                PortfolioAccount.workspace_id == workspace_id,
                PortfolioAccount.portfolio_id == portfolio_id,
            )
        )
    ).scalars().all()
    return {link.financial_account_id for link in links}


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
    as_of: date | None = None,
    currency: str | None = None,
) -> PortfolioValuationOut:
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_as_of = as_of or date.today()
    account_ids = await _resolve_account_ids(db, workspace_id, portfolio_id)
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
    )


@router.get("/analytics/allocation", response_model=PortfolioAllocationOut)
async def get_portfolio_allocation(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    portfolio_id: uuid.UUID | None = None,
    as_of: date | None = None,
    currency: str | None = None,
) -> PortfolioAllocationOut:
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_as_of = as_of or date.today()
    account_ids = await _resolve_account_ids(db, workspace_id, portfolio_id)
    allocation = await portfolio_analytics.compute_allocation(
        db, workspace_id, account_ids, resolved_as_of, resolved_currency
    )

    def to_items(items):
        return [AllocationItemOut(key=i.key, label=i.label, value=i.value, share=i.share) for i in items]

    return PortfolioAllocationOut(
        currency=allocation.currency,
        as_of=resolved_as_of,
        has_market_data=allocation.has_market_data,
        by_asset_type=to_items(allocation.by_asset_type),
        by_asset=to_items(allocation.by_asset),
        by_account=to_items(allocation.by_account),
    )


@router.get("/analytics/performance", response_model=PortfolioPerformanceOut)
async def get_portfolio_performance(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    portfolio_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> PortfolioPerformanceOut:
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_to = date_to or date.today()
    resolved_from = date_from or (resolved_to - timedelta(days=365))
    if portfolio_id is not None:
        await _get_portfolio_or_404(db, workspace_id, portfolio_id)
    snapshots = await portfolio_analytics.list_portfolio_snapshots(
        db, workspace_id, portfolio_id, resolved_from, resolved_to
    )
    return PortfolioPerformanceOut(
        currency=resolved_currency,
        points=[
            PortfolioSnapshotPointOut(
                snapshot_date=s.snapshot_date,
                market_value=s.market_value,
                cost_basis=s.cost_basis,
                unrealized_pl=s.unrealized_pl,
                realized_pl=s.realized_pl,
                has_market_data=s.has_market_data,
            )
            for s in snapshots
            if s.currency == resolved_currency
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
    return await _get_portfolio_or_404(db, workspace_id, portfolio_id)


@router.patch("/{portfolio_id}", response_model=PortfolioOut)
async def update_portfolio(
    portfolio_id: uuid.UUID,
    payload: PortfolioUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Portfolio:
    portfolio = await _get_portfolio_or_404(db, workspace_id, portfolio_id)
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
    portfolio = await _get_portfolio_or_404(db, workspace_id, portfolio_id)
    await db.delete(portfolio)
    await db.commit()


# --- conti associati (SPEC §36: portfolio aggregabili su piu' conti) -----------


@router.get("/{portfolio_id}/accounts", response_model=list[PortfolioAccountOut])
async def list_portfolio_accounts(
    portfolio_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[PortfolioAccount]:
    await _get_portfolio_or_404(db, workspace_id, portfolio_id)
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
    await _get_portfolio_or_404(db, workspace_id, portfolio_id)
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
    await _get_portfolio_or_404(db, workspace_id, portfolio_id)
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

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
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
    MerchantBreakdownItemOut,
    MerchantBreakdownOut,
    PeriodOut,
    SummaryOut,
)
from app.schemas.portfolio_analytics import NetWorthHistoryOut, NetWorthSnapshotPointOut
from app.services import analytics as analytics_service
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
) -> CategoryBreakdownOut:
    date_from, date_to = _resolve_period(date_from, date_to)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    items = await analytics_service.by_category(
        db, workspace_id, resolved_currency, direction, date_from, date_to, financial_account_id
    )
    return CategoryBreakdownOut(
        currency=resolved_currency,
        direction=direction,
        period=PeriodOut(date_from=date_from, date_to=date_to),
        items=[CategoryBreakdownItemOut(**i) for i in items],
    )


@router.get("/net-worth-history", response_model=NetWorthHistoryOut)
async def get_net_worth_history(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> NetWorthHistoryOut:
    """Storico patrimonio (SPEC §31) — legge SEMPRE dagli snapshot gia'
    scritti (`net_worth_snapshots`, cron/trigger manuale), mai ricalcolato
    da zero: a differenza di `/balance-history` (M08, ricostruito a
    ritroso dalle sole transazioni), qui il patrimonio include gli
    investimenti a valore di mercato, che non e' derivabile dalle sole
    transazioni bancarie (DoD M09)."""
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    resolved_to = date_to or date.today()
    resolved_from = date_from or (resolved_to - timedelta(days=365))
    snapshots = await portfolio_analytics.list_net_worth_snapshots(
        db, workspace_id, resolved_from, resolved_to
    )
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
            for s in snapshots
            if s.currency == resolved_currency
        ],
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

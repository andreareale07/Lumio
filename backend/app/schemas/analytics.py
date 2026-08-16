import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.services.analytics_calc import GRANULARITIES


class PeriodOut(BaseModel):
    date_from: date
    date_to: date


class SummaryOut(BaseModel):
    currency: str
    period: PeriodOut
    comparison_period: PeriodOut
    liquidity: Decimal
    debt: Decimal
    investments: Decimal
    net_worth: Decimal
    has_investments: bool
    income: Decimal
    expenses: Decimal
    net_cash_flow: Decimal
    previous_income: Decimal
    previous_expenses: Decimal
    previous_net_cash_flow: Decimal


class AccountBalanceOut(BaseModel):
    financial_account_id: uuid.UUID
    name: str
    account_type: str
    balance: Decimal


class BalancesOut(BaseModel):
    currency: str
    as_of: date
    accounts: list[AccountBalanceOut]
    liquidity_total: Decimal
    debt_total: Decimal
    investment_total: Decimal
    has_investments: bool


class BalanceHistoryPointOut(BaseModel):
    period: date
    balance: Decimal


class BalanceHistoryOut(BaseModel):
    currency: str
    granularity: str
    period: PeriodOut
    points: list[BalanceHistoryPointOut]


class CashFlowPointOut(BaseModel):
    period: date
    income: Decimal
    expenses: Decimal
    net: Decimal


class CashFlowOut(BaseModel):
    currency: str
    granularity: str
    period: PeriodOut
    points: list[CashFlowPointOut]


class CategoryBreakdownItemOut(BaseModel):
    category_id: uuid.UUID | None
    name: str
    total: Decimal
    share: Decimal
    transactions_count: int


class CategoryBreakdownOut(BaseModel):
    currency: str
    direction: str
    period: PeriodOut
    items: list[CategoryBreakdownItemOut]


class MerchantBreakdownItemOut(BaseModel):
    merchant: str
    total: Decimal
    share: Decimal
    transactions_count: int


class MerchantBreakdownOut(BaseModel):
    currency: str
    direction: str
    period: PeriodOut
    items: list[MerchantBreakdownItemOut]


# Riesportata cosi' che il router possa validare il parametro `granularity`
# in query senza importare direttamente il modulo di calcolo puro.
__all__ = [
    "GRANULARITIES",
    "PeriodOut",
    "SummaryOut",
    "AccountBalanceOut",
    "BalancesOut",
    "BalanceHistoryPointOut",
    "BalanceHistoryOut",
    "CashFlowPointOut",
    "CashFlowOut",
    "CategoryBreakdownItemOut",
    "CategoryBreakdownOut",
    "MerchantBreakdownItemOut",
    "MerchantBreakdownOut",
]

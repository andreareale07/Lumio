from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PortfolioValuationOut(BaseModel):
    currency: str
    as_of: date
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool
    has_holdings: bool


class AllocationItemOut(BaseModel):
    key: str
    label: str
    value: Decimal
    share: Decimal


class PortfolioAllocationOut(BaseModel):
    currency: str
    as_of: date
    has_market_data: bool
    by_asset_type: list[AllocationItemOut]
    by_asset: list[AllocationItemOut]
    by_account: list[AllocationItemOut]
    by_strategy: list[AllocationItemOut]


class PortfolioSnapshotPointOut(BaseModel):
    snapshot_date: date
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool


class PortfolioPerformanceOut(BaseModel):
    currency: str
    points: list[PortfolioSnapshotPointOut]


class NetWorthSnapshotPointOut(BaseModel):
    snapshot_date: date
    liquidity: Decimal
    debt: Decimal
    investments: Decimal
    net_worth: Decimal


class NetWorthHistoryOut(BaseModel):
    currency: str
    points: list[NetWorthSnapshotPointOut]

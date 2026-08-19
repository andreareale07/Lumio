import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PortfolioSummaryItemOut(BaseModel):
    portfolio_id: uuid.UUID
    name: str
    account_count: int
    currency: str
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    has_market_data: bool
    has_holdings: bool


class PortfolioSummaryListOut(BaseModel):
    as_of: date
    items: list[PortfolioSummaryItemOut]


class PositionValuationOut(BaseModel):
    position_id: uuid.UUID
    asset_id: uuid.UUID
    asset_label: str
    financial_account_id: uuid.UUID
    account_label: str
    quantity: Decimal
    average_cost: Decimal
    currency: str
    # Valuta con cui l'utente ha registrato la posizione (`Position.
    # currency`) — sempre esposta accanto al valore convertito in
    # `currency`, mai persa dietro la conversione.
    currency_native: str
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool


class PortfolioPositionsOut(BaseModel):
    currency: str
    as_of: date
    has_market_data: bool
    has_missing_fx_rate: bool = False
    positions: list[PositionValuationOut]


class PortfolioValuationOut(BaseModel):
    currency: str
    as_of: date
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool
    has_holdings: bool
    # Sistema di valute: True se una posizione in valuta diversa da
    # `currency` e' stata esclusa dal totale per mancanza di un tasso di
    # cambio — mai un'esclusione invisibile (vedi portfolio_analytics.py).
    has_missing_fx_rate: bool = False


class AssetValuationOut(BaseModel):
    currency: str
    quantity: Decimal
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool
    # Sistema di valute: True se il prezzo o la posizione sono in una valuta
    # diversa da `currency` e nessun tasso di cambio e' disponibile per
    # convertirli — mai un'esclusione invisibile (vedi portfolio_analytics.py).
    has_missing_fx_rate: bool = False
    # Prezzo per unita' convertito in `currency` (None se nessun prezzo o
    # tasso disponibile) + l'originale del provider, sempre esposto: la UI
    # mostra il convertito come valore principale e l'originale al passaggio
    # del mouse, mai l'uno al posto dell'altro.
    price: Decimal | None = None
    price_native: Decimal | None = None
    price_native_currency: str | None = None


class AllocationItemOut(BaseModel):
    key: str
    label: str
    value: Decimal
    share: Decimal


class PortfolioAllocationOut(BaseModel):
    currency: str
    as_of: date
    has_market_data: bool
    has_missing_fx_rate: bool = False
    by_asset_type: list[AllocationItemOut]
    by_asset: list[AllocationItemOut]
    by_account: list[AllocationItemOut]
    by_currency: list[AllocationItemOut] = []
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

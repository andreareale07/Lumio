import uuid
from datetime import date, datetime
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
    # Conteggio dopo il filtro (`realized_only`/`asset_id`/`financial_account_id`),
    # PRIMA della paginazione — additivo, il consumer esistente
    # (`PortfolioDetailPage`, senza paginazione) lo ignora senza rompersi.
    total: int = 0


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
    # docs/SPEC_STOCK_PRICE.md: presenti SOLO quando `price`/`price_native`
    # vengono da una live-quote (cache Redis + eventuale fallback), non dal
    # prezzo daily canonico — mai confuso con l'istante di scrittura di
    # `asset_prices`. `is_stale=True` quando il provider non ha risposto in
    # tempo e si e' mostrato l'ultimo valore noto (mai un errore, vedi
    # `app/services/live_quote_service.py`).
    price_quoted_at: datetime | None = None
    price_is_live: bool = False
    price_is_stale: bool = False


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
    # FETTA 3 (storico patrimonio ricostruito): True se almeno uno snapshot
    # nell'intervallo richiesto e' stato scartato perche' la sua `currency`
    # non coincide con quella risolta (bug latente gia' presente prima di
    # questa fetta: cambiare `base_currency` del workspace svuota
    # silenziosamente questo grafico, vedi `api/v1/analytics.py`) — rende
    # onesto quel filtro, cosi' la UI puo' proporre "ricostruisci lo
    # storico" invece di mostrare un grafico vuoto senza spiegazione.
    has_mixed_currency: bool = False

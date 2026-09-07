import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.asset import ASSET_TYPES


class AssetCreate(BaseModel):
    symbol: str | None = Field(default=None, max_length=32)
    isin: str | None = Field(default=None, max_length=12)
    name: str = Field(min_length=1, max_length=200)
    asset_type: str = Field(pattern="^(" + "|".join(ASSET_TYPES) + ")$")
    currency: str = Field(min_length=3, max_length=3)
    notes: str | None = None


class AssetUpdate(BaseModel):
    symbol: str | None = Field(default=None, max_length=32)
    isin: str | None = Field(default=None, max_length=12)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    asset_type: str | None = Field(default=None, pattern="^(" + "|".join(ASSET_TYPES) + ")$")
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None


class AssetOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    symbol: str | None
    isin: str | None
    name: str
    asset_type: str
    currency: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # Nome "pulito" secondo il market data provider attivo (es. "Apple
    # Inc."), dalla cache di `asset_profiles` (Step 3) — MAI una
    # sovrascrittura di `name` (il dato grezzo estratto dal parser Trade
    # Republic, spesso con suffissi di borsa tedeschi tipo "DL-,0001").
    # `None` finche' nessuno ha ancora aperto il dettaglio di questo asset
    # (la cache si popola on-demand, non in blocco per non moltiplicare le
    # chiamate a un endpoint gia' fragile — vedi asset_profile_service.py).
    display_name: str | None = None

    model_config = {"from_attributes": True}


class ClosedPortionOut(BaseModel):
    quantity: Decimal
    sell_transaction_id: uuid.UUID
    sell_trade_date: date
    proceeds: Decimal
    cost_basis: Decimal
    gain_or_loss: Decimal


class LotBreakdownRowOut(BaseModel):
    """Scomposizione aperto/chiuso di un acquisto (feature portfolio — quale
    porzione e' stata venduta, contro quale prezzo, e quanta ne resta
    ancora posseduta). Il criterio di abbinamento acquisto/vendita e'
    quello della giurisdizione fiscale corrente, non un valore fisso."""

    transaction_id: uuid.UUID
    financial_account_id: uuid.UUID
    trade_date: date
    quantity: Decimal
    price: Decimal
    open_quantity: Decimal
    closed_portions: list[ClosedPortionOut]


class RealizedPortionTaxOut(BaseModel):
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID
    tax_due: Decimal | None
    taxable_amount: Decimal | None
    offset_amount: Decimal | None
    excluded_reason: str | None


class OpenLotTaxPreviewOut(BaseModel):
    transaction_id: uuid.UUID
    financial_account_id: uuid.UUID
    sequence: int
    cumulative_quantity: Decimal
    cumulative_gain: Decimal
    tax_due: Decimal | None
    taxable_amount: Decimal | None
    offset_amount: Decimal | None
    excluded_reason: str | None


class AssetTaxPreviewOut(BaseModel):
    """Colonna "Tasse" di `AssetDetailPage`: `realized` riusa il numero
    REALE gia' calcolato per gli eventi gia' venduti, `open_cumulative` e'
    una simulazione "se vendessi oggi" cumulativa in ordine di consumo
    fiscale (LIFO/FIFO) per i lotti ancora aperti — mai un numero per riga
    scollegato dagli altri, la capienza dello zainetto e' condivisa."""

    realized: list[RealizedPortionTaxOut]
    open_cumulative: list[OpenLotTaxPreviewOut]

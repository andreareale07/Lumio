import uuid
from datetime import datetime

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

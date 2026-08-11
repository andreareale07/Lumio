import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

MarketDataProviderName = Literal["manual", "stooq", "yahoo", "custom"]


class MarketDataProfileCreate(BaseModel):
    name: str
    provider: MarketDataProviderName
    endpoint: str | None = None
    api_key: str | None = None
    price_field: str | None = None
    currency_field: str | None = None


class MarketDataProfileUpdate(BaseModel):
    """`provider` non e' modificabile (vedi `app/models/market_data_profile.py`):
    cambiarlo richiede creare un nuovo profilo. `api_key`: `None` = mantieni
    la chiave gia' salvata, stringa vuota = rimuovila, stringa non vuota =
    sostituiscila."""

    name: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    price_field: str | None = None
    currency_field: str | None = None


class MarketDataProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    provider: MarketDataProviderName
    endpoint: str | None
    api_key_set: bool
    price_field: str | None
    currency_field: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MarketDataConnectionCheckRequest(BaseModel):
    """Payload di `POST /settings/market-data/test` per un profilo NON
    ANCORA salvato — vedi `AIConnectionCheckRequest` per lo stesso pattern
    lato AI (M07)."""

    provider: MarketDataProviderName
    endpoint: str | None = None
    api_key: str | None = None
    price_field: str | None = None
    currency_field: str | None = None


class MarketDataTestConnectionResult(BaseModel):
    success: bool
    message: str


class AssetPriceCreate(BaseModel):
    price_date: date
    price: Decimal
    currency: str


class MarketDataRefreshTriggered(BaseModel):
    """Risposta del trigger manuale (`POST /settings/market-data/refresh`):
    il job gira in background (SPEC/CLAUDE.md "mai bloccare la request
    HTTP"), qui non c'e' pero' un canale di progresso live come per gli
    import (SPEC §51) — una singola operazione di fetch prezzi non ha
    stadi intermedi che valga la pena mostrare passo-passo, a differenza del
    parsing di un PDF. Il frontend puo' semplicemente ri-eseguire le query
    dopo qualche secondo."""

    job_id: str


class AssetPriceOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    price_date: date
    price: Decimal
    currency: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}

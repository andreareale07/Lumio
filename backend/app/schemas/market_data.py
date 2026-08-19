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


class PricePointOut(BaseModel):
    """`at` e' sempre l'istante completo, anche per i preset giornalieri
    (mezzanotte UTC in quel caso) — i preset intraday (1G/1S) hanno bisogno
    dell'ora per non collassare tutti i punti di una giornata sulla stessa
    etichetta nel grafico."""

    at: datetime
    price: Decimal


class PriceHistoryOut(BaseModel):
    """Risposta di `GET /assets/{id}/price-history`. `supports_history=False`
    distingue "questo provider non fa storico" (es. profilo manuale/stooq/
    custom) da `points=[]` ("il provider lo supporta ma non ha dati per
    questo range") — casi che il frontend deve mostrare diversamente."""

    preset: str
    supports_history: bool
    currency: str
    points: list[PricePointOut]


class AssetProfileOut(BaseModel):
    """Arricchimento best-effort (Step 3) — ogni campo puo' essere `None`
    (dato non disponibile, mai "N/A" ne' un errore). `fetched_at=None`
    significa "nessun dato mai ottenuto per questo asset"."""

    issuer: str | None
    category: str | None
    aum: Decimal | None
    distribution_policy: str | None
    # Nome "pulito" secondo il provider (es. "Apple Inc.") — MAI una
    # sovrascrittura di Asset.name, solo un'alternativa opzionale per la UI.
    display_name: str | None = None
    fetched_at: datetime | None

    model_config = {"from_attributes": True}


class AssetPriceOut(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    price_date: date
    price: Decimal
    currency: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}

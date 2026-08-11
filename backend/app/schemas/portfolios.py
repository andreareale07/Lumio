import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    currency: str = Field(min_length=3, max_length=3)


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class PortfolioOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PortfolioAccountCreate(BaseModel):
    financial_account_id: uuid.UUID


class PortfolioAccountOut(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    financial_account_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class SnapshotRebuildTriggered(BaseModel):
    """Risposta del trigger manuale (`POST /portfolios/snapshots/rebuild`,
    DoD M09) — stesso principio di `MarketDataRefreshTriggered`: job async,
    nessun canale SSE dedicato."""

    job_id: str

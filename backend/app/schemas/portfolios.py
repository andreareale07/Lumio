import uuid
from datetime import date, datetime

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


class SnapshotBackfillRequest(BaseModel):
    """Body opzionale del trigger manuale (`POST /portfolios/snapshots/
    backfill`, FETTA 3) — `date_from=None` (default, corpo assente) =
    "ricostruisci l'intero storico disponibile" (il job determina l'inizio
    da `LEAST(MIN(transactions...), MIN(investment_transactions...))`,
    clampato a `snapshot_backfill_max_years`)."""

    date_from: date | None = None


class SnapshotBackfillTriggered(BaseModel):
    """Risposta del trigger (automatico a fine import o manuale) del
    backfill storico patrimonio — a differenza di `SnapshotRebuildTriggered`
    (secondi), questo job puo' impiegare minuti/ore: il progresso live vive
    nel cruscotto Attivita' (`GET /portfolios/snapshots/backfill/events`),
    non in un canale dedicato su questa pagina."""

    job_id: str

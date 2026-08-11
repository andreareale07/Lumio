import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# SPEC §33: tipologie concettuali iniziali, non tutte necessariamente usate
# da subito — l'architettura deve solo essere estendibile.
ASSET_TYPES = ("etf", "stock", "bond", "crypto", "fund", "cash", "other")


class Asset(Base):
    """Milestone 09 — catalogo asset per workspace (SPEC §33).

    Scoped al workspace, NON globale come `banks`: un catalogo condiviso fra
    tenant esporrebbe a tutti un asset creato/nominato da un singolo utente,
    e non esiste un catalogo canonico (ISIN registry) da seedare in questa
    fase. `symbol`/`isin` sono opzionali: un asset "Other" (es. una quota di
    fondo privato) puo' non avere nessuno dei due, e in tal caso non e'
    risolvibile da nessun `MarketDataProvider` — valorizzazione sempre a
    costo per quell'asset (gestito in `app/services/portfolio_analytics.py`,
    M09b).
    """

    __tablename__ = "assets"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('etf', 'stock', 'bond', 'crypto', 'fund', 'cash', 'other')",
            name="ck_assets_asset_type",
        ),
        # Abilita le FK composite da `investment_transactions`/`positions`
        # (SPEC §57).
        UniqueConstraint("workspace_id", "id", name="uq_assets_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    isin: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    asset_type: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

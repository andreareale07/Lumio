import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# "none"/"manual" scrivono qui con source diverse: "manual" per un prezzo
# inserito a mano, le altre per un fetch riuscito. Nessuna riga "none" (un
# provider disabilitato non scrive nulla).
ASSET_PRICE_SOURCES = ("manual", "stooq", "yahoo", "custom")


class AssetPrice(Base):
    """Milestone 09b — storico prezzi per asset (SPEC §38).

    Sia i prezzi inseriti a mano sia quelli scaricati da un provider finiscono
    qui, nella stessa tabella: chi valorizza una posizione
    (`app/services/portfolio_analytics.py`) legge sempre da qui, mai
    direttamente da un provider — un prezzo resta disponibile anche se il
    provider che l'ha scaricato va offline o il profilo viene disattivato.
    Un solo prezzo per (asset, giorno): un nuovo fetch/inserimento nello
    stesso giorno sovrascrive (upsert), non accumula duplicati.
    """

    __tablename__ = "asset_prices"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'stooq', 'yahoo', 'custom')", name="ck_asset_prices_source"
        ),
        UniqueConstraint("workspace_id", "asset_id", "price_date", name="uq_asset_prices_asset_date"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_prices_workspace_asset",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # A differenza di `created_at` (mai toccato da un upsert successivo),
    # questo riflette l'ultimo fetch/salvataggio riuscito — usato per la
    # cache-first di GET /assets/{id}/price-history (TTL 15 minuti prima di
    # ricontattare Yahoo per lo stesso giorno).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

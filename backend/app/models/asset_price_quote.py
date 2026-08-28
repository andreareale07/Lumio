import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# "manual" escluso di proposito: il profilo manuale non produce mai una
# quotazione live (vedi ManualMarketDataProvider.fetch_quote -> None), quindi
# non ha senso tra le sorgenti di un'osservazione intraday.
ASSET_PRICE_QUOTE_SOURCES = ("stooq", "yahoo", "custom")


class AssetPriceQuote(Base):
    """Intraday osservato (docs/SPEC_STOCK_PRICE.md) — una riga per OGNI
    quotazione realmente scaricata dal provider (mai un upsert su un valore
    corrente): a differenza di `AssetPrice` (daily canonico, 1 riga/giorno,
    fonte di verita' per valorizzazione/snapshot), questa tabella e'
    puramente osservativa e non viene MAI letta da
    `app/services/portfolio_analytics.py`. Popolata da
    `app/services/live_quote_service.py` (cache miss della live-quote) e dal
    fallback dello storico "1G"/"1S" in `app/api/v1/assets.py`. Retention
    breve (3 giorni, vedi `app/worker/jobs/market_data.py`): serve solo ad
    arricchire il grafico intraday del giorno corrente, non e' uno storico
    a lungo termine.
    """

    __tablename__ = "asset_price_quotes"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "source IN ('stooq', 'yahoo', 'custom')", name="ck_asset_price_quotes_source"
        ),
        UniqueConstraint(
            "workspace_id", "asset_id", "quoted_at", name="uq_asset_price_quotes_asset_quoted_at"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_price_quotes_workspace_asset",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

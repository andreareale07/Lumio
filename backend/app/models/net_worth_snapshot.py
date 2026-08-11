import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NetWorthSnapshot(Base):
    """Milestone 09b — storico patrimonio (SPEC §31): `Net Worth = Cash +
    Investments + Other Assets - Liabilities`. Separata da
    `PortfolioSnapshot`: risponde a una domanda diversa (patrimonio
    complessivo del workspace, non il valore di un singolo raggruppamento di
    conti) e non ha un portfolio di riferimento. Un solo snapshot per giorno
    per workspace (upsert, non accumulo)."""

    __tablename__ = "net_worth_snapshots"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("workspace_id", "snapshot_date", name="uq_net_worth_snapshots_workspace_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    liquidity: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    debt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    investments: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    net_worth: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

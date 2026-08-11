import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKeyConstraint, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortfolioSnapshot(Base):
    """Milestone 09b — storico valore/performance di un portfolio (SPEC §31,
    §37). `portfolio_id` NULL rappresenta l'aggregato implicito "tutti i
    conti" (vedi `Portfolio`, mai una riga vera in `portfolios` per quella
    vista) — l'unicita' per questo caso e' garantita da un indice parziale
    dedicato in migration (NULL non e' mai "uguale" a se stesso in un
    UNIQUE/PRIMARY KEY standard).

    Scritta da un job schedulato o da un refresh manuale
    (`app/worker/jobs/market_data.py`), mai ricalcolata da zero a ogni
    richiesta (DoD M09: "storico patrimonio consultabile via snapshot").
    `has_market_data=False` quando almeno un asset del portfolio non ha un
    prezzo disponibile in quel giorno: `market_value` in quel caso coincide
    con `cost_basis` per gli asset senza prezzo — mai un crash, il dato e'
    onestamente marcato come stimato a costo.
    """

    __tablename__ = "portfolio_snapshots"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            ondelete="CASCADE",
            name="fk_portfolio_snapshots_workspace_portfolio",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unrealized_pl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    realized_pl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    has_market_data: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

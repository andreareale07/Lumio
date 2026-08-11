import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortfolioAccount(Base):
    """Milestone 09 — join M2M `portfolios` ↔ `financial_accounts` (SPEC §36).

    Entrambe le FK sono composite su `(workspace_id, ...)` (SPEC §57): un
    conto o un portfolio di un altro workspace non possono mai finire nella
    stessa riga, indipendentemente da bug applicativi o dalla sola RLS.
    """

    __tablename__ = "portfolio_accounts"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "portfolio_id",
            "financial_account_id",
            name="uq_portfolio_accounts_portfolio_account",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            ondelete="CASCADE",
            name="fk_portfolio_accounts_workspace_portfolio",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_portfolio_accounts_workspace_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

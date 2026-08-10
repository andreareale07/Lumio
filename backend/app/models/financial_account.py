import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACCOUNT_TYPES = ("checking", "savings", "brokerage", "cash", "credit_card", "other")


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"
    # eager_defaults: updated_at ha un onupdate lato server: senza questo,
    # dopo un UPDATE l'attributo resta "expired" e un accesso successivo
    # richiederebbe un lazy load — impossibile fuori dal contesto async in
    # cui e' avvenuto il flush (es. durante la serializzazione della
    # response FastAPI). Con eager_defaults SQLAlchemy aggiunge RETURNING
    # all'UPDATE stesso, popolando il valore senza query aggiuntive.
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('checking', 'savings', 'brokerage', 'cash', 'credit_card', 'other')",
            name="ck_financial_accounts_account_type",
        ),
        # Consente la FK composita da `transactions` (workspace_id, financial_account_id)
        # -> (workspace_id, id): garanzia DB reale contro relazioni cross-tenant
        # (SPEC §57), non solo affidata alla RLS.
        UniqueConstraint("workspace_id", "id", name="uq_financial_accounts_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("banks.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    account_type: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    account_identifier_masked: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

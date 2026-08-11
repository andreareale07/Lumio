import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancialAccountIbanHistory(Base):
    """Milestone 09.5c: IBAN PRECEDENTI di un conto — un istituto puo'
    cambiare l'IBAN di un conto esistente (es. migrazione DE->IT osservata
    su Trade Republic) e gli estratti conto passati riportano ancora il
    vecchio IBAN come controparte dei bonifici. Popolata automaticamente
    da `app/api/v1/accounts.py` quando l'utente cambia l'IBAN di un conto
    (mai una lista da compilare a mano) — il riconoscimento
    (`app/services/transfer_recognition.py`) controlla sia questa tabella
    sia `financial_accounts.iban` (il valore attuale)."""

    __tablename__ = "financial_account_iban_history"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "financial_account_id", "iban", name="uq_iban_history_account_iban"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iban: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

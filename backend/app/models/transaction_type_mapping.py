import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.transaction import TRANSACTION_TYPES


class TransactionTypeMapping(Base):
    """Milestone 09.5 — override configurabile dall'utente della mappatura
    `source_type_raw` -> `transaction_type` di UN parser (SPEC §17,
    `parser_type` combacia con `BankParser.parser_type`), per workspace.

    Il default hardcoded del parser (es.
    `TradeRepublicParser.default_transaction_type`) resta il fallback
    quando non esiste nessuna riga qui — vedi
    `app/services/transaction_type_mapping_service.py:resolve_transaction_type`.
    A differenza del default del parser (che non assume mai `transfer`,
    regola di design di M09), qui l'utente PUO' scegliere `transfer` come
    target: e' una scelta esplicita sua, non un'assunzione del sistema."""

    __tablename__ = "transaction_type_mappings"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN (" + ", ".join(f"'{t}'" for t in TRANSACTION_TYPES) + ")",
            name="ck_transaction_type_mappings_type",
        ),
        UniqueConstraint(
            "workspace_id", "parser_type", "source_type_raw", name="uq_transaction_type_mappings_label"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parser_type: Mapped[str] = mapped_column(String, nullable=False)
    source_type_raw: Mapped[str] = mapped_column(String, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

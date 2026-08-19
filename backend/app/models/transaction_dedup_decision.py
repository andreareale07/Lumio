import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEDUP_DECISIONS = ("confirmed_distinct", "confirmed_duplicate")


class TransactionDedupDecision(Base):
    """Relazione persistente, decisa dall'utente, tra un candidato ambiguo
    (il fingerprint di una riga vista in REVIEW) e una transazione esistente
    specifica — docs/SPEC_DEDUP_TRANSACTION.md §17. Mai una modifica del
    fingerprint della transazione esistente: questa tabella e' l'unico posto
    dove la decisione vive, cosi' lo stesso caso ambiguo non viene
    riproposto in un futuro import (vedi app/services/transaction_dedup.py,
    `_find_dedup_decision`).

    'confirmed_distinct' = l'utente ha scelto "IMPORTA COMUNQUE" (i due
    record sono transazioni realmente distinte). 'confirmed_duplicate' =
    l'utente ha scelto "NON IMPORTARE" (il nuovo record e' lo stesso
    movimento del candidato esistente, nonostante il fingerprint diverso).
    """

    __tablename__ = "transaction_dedup_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('confirmed_distinct', 'confirmed_duplicate')",
            name="ck_transaction_dedup_decisions_decision",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_transaction_dedup_decisions_workspace_account",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "existing_transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="CASCADE",
            name="fk_transaction_dedup_decisions_workspace_transaction",
        ),
        # Nullable (una decisione resta valida anche se l'import che l'ha
        # generata viene poi eliminato, stesso principio di
        # `imports.import_mapping_id` -> MATCH SIMPLE soddisfatto quando la
        # colonna referenziante e' NULL): serve solo per l'audit (SPEC §33),
        # mai per la logica di matching.
        ForeignKeyConstraint(
            ["workspace_id", "source_import_id"],
            ["imports.workspace_id", "imports.id"],
            ondelete="SET NULL",
            name="fk_transaction_dedup_decisions_workspace_import",
        ),
        UniqueConstraint(
            "workspace_id",
            "financial_account_id",
            "existing_transaction_id",
            "new_fingerprint",
            name="uq_transaction_dedup_decisions_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    existing_transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    new_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    source_import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

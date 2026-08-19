import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

REVIEW_ITEM_STATUSES = ("pending", "confirmed_new", "confirmed_duplicate")


class TransactionReviewItem(Base):
    """Riga di un import per cui il Deduplication Engine non ha trovato un
    match esatto per fingerprint ma ha trovato un candidato ambiguo con lo
    stesso "core key" (conto+data+importo+currency+tipo) e descrizione
    diversa — docs/SPEC_DEDUP_TRANSACTION.md §15/§16.

    Mantiene lo snapshot completo della `ParsedRow` (nessuna `Transaction`
    esiste ancora per una riga 'pending') cosi' che, se l'utente sceglie
    "IMPORTA COMUNQUE", si possa persisterla con la STESSA pipeline di
    `app/services/transaction_persistence.py` usata per le righe NEW di un
    import normale — mai una scrittura parallela parziale (verifica
    esplicita del piano approvato, §6).

    `ondelete=CASCADE` su `import_id`: eliminare un import in
    'ready_for_review' pulisce anche le review pendenti mai persistite come
    `Transaction` — nessun dato finanziario confermato viene perso, solo
    candidati mai scritti.
    """

    __tablename__ = "transaction_review_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed_new', 'confirmed_duplicate')",
            name="ck_transaction_review_items_status",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "import_id"],
            ["imports.workspace_id", "imports.id"],
            ondelete="CASCADE",
            name="fk_transaction_review_items_workspace_import",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_transaction_review_items_workspace_account",
        ),
        # Nullable + SET NULL: il candidato esistente puo' in teoria essere
        # eliminato singolarmente (DELETE /transactions/{id}) mentre una
        # review resta pendente — l'item non deve mai bloccare quella delete
        # (nessun RESTRICT), la review resta comunque visibile/decidibile
        # (senza confronto) invece di sparire silenziosamente.
        ForeignKeyConstraint(
            ["workspace_id", "candidate_existing_transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="SET NULL",
            name="fk_transaction_review_items_workspace_candidate",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "resolved_transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="SET NULL",
            name="fk_transaction_review_items_workspace_resolved",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    import_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Snapshot ParsedRow (app/services/csv_import.py) — solo per poter
    # costruire la Transaction se la review viene confermata come NEW.
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description_raw: Mapped[str] = mapped_column(String, nullable=False)
    description_normalized: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String, nullable=False)
    source_type_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    reference: Mapped[str | None] = mapped_column(String, nullable=True)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(String, nullable=True)
    counterparty_iban: Mapped[str | None] = mapped_column(String, nullable=True)

    new_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_existing_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    # True quando l'esito e' stato applicato automaticamente da una
    # `TransactionDedupDecision` preesistente (SPEC §17), senza chiedere di
    # nuovo all'utente — mai per le review effettivamente pendenti.
    auto_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    dedup_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transaction_dedup_decisions.id"), nullable=True
    )
    resolved_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

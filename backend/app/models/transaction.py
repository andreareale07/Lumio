import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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

TRANSACTION_TYPES = (
    "expense",
    "income",
    "transfer",
    "investment",
    "dividend",
    "interest",
    "fee",
    "tax",
    "refund",
    "adjustment",
)
DIRECTIONS = ("debit", "credit")
STATUSES = ("pending", "confirmed")


class Transaction(Base):
    __tablename__ = "transactions"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ("
            "'expense', 'income', 'transfer', 'investment', 'dividend', "
            "'interest', 'fee', 'tax', 'refund', 'adjustment'"
            ")",
            name="ck_transactions_transaction_type",
        ),
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_transactions_direction"),
        CheckConstraint("status IN ('pending', 'confirmed')", name="ck_transactions_status"),
        # FK composita: garantisce a livello DB che il conto referenziato
        # appartenga allo stesso workspace della transazione (SPEC §57), non
        # solo che esista un conto con quell'id in un workspace qualsiasi.
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_transactions_workspace_account",
        ),
        # category_id NON ha FK composita: puo' puntare a una categoria di
        # sistema (workspace_id NULL) oltre a una del proprio workspace. La
        # FK semplice su categories.id, combinata con la RLS su categories,
        # e' comunque sufficiente contro il cross-tenant: Postgres valuta il
        # vincolo FK sotto lo stesso ruolo della sessione (lumio_app, senza
        # BYPASSRLS), quindi una categoria privata di un altro workspace non
        # e' "visibile" alla verifica del vincolo e l'insert fallisce.
        # Verificato esplicitamente in test_rls_accounts_transactions.py.
        # import_id (milestone 04): FK composita come financial_account_id,
        # ON DELETE RESTRICT — cancellare un import non deve mai cancellare
        # o orfanizzare silenziosamente transazioni finanziarie reali. Nessun
        # endpoint DELETE su imports esiste in M04 per questo motivo.
        ForeignKeyConstraint(
            ["workspace_id", "import_id"],
            ["imports.workspace_id", "imports.id"],
            ondelete="RESTRICT",
            name="fk_transactions_workspace_import",
        ),
        # Milestone 09: abilita la FK composita da
        # `investment_transactions.transaction_id` (link opzionale verso la
        # transazione bancaria corrispondente, SPEC §57).
        UniqueConstraint("workspace_id", "id", name="uq_transactions_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description_raw: Mapped[str] = mapped_column(String, nullable=False)
    description_normalized: Mapped[str | None] = mapped_column(String, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String, nullable=True)
    reference: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String, nullable=False)
    # Etichetta grezza del provider per il "tipo" (es. "Bonifico", "Commercio"
    # per Trade Republic) — MAI usata dal codice applicativo per decisioni,
    # solo conservata (CLAUDE.md: "conservare sempre il dato raw insieme al
    # normalizzato"). `transaction_type` sopra e' il vocabolario canonico
    # provider-agnostico su cui girano regole/AI/analytics; questo campo
    # serve a poter rimappare in futuro senza dover reimportare (M09.5).
    # Nullable: il canale CSV storico e gli import precedenti a questa
    # colonna non la popolano.
    source_type_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'confirmed'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

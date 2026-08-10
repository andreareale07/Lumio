import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# SPEC §19 elenca 9 stati. In milestone 04 (nessun rules engine, nessuna AI
# ancora disponibili — arrivano in M06/M07) la macchina a stati realmente
# raggiungibile e':
#   uploaded -> queued -> processing -> parsing -> completed | failed
#   uploaded | queued -> cancelled
# `classifying` e `ready_for_review` restano nel CHECK constraint (la SPEC li
# richiede) ma sono deliberatamente irraggiungibili finche' non esiste una
# vera classificazione da rivedere: usarli ora sarebbe uno stato finto.
IMPORT_STATUSES = (
    "uploaded",
    "queued",
    "processing",
    "parsing",
    "classifying",
    "ready_for_review",
    "completed",
    "failed",
    "cancelled",
)


class Import(Base):
    __tablename__ = "imports"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in IMPORT_STATUSES) + ")",
            name="ck_imports_status",
        ),
        # Stesso pattern di `transactions` -> `financial_accounts` (M03):
        # garanzia DB reale, non solo applicativa/RLS, che il conto
        # referenziato appartenga allo stesso workspace dell'import.
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_imports_workspace_account",
        ),
        # import_mapping_id e' nullable (si puo' importare con una mappatura
        # "usa e getta" mai salvata) quindi, come per import_mappings stessa,
        # MATCH SIMPLE rende il vincolo satisfied quando la colonna e' NULL:
        # nessun trigger necessario.
        ForeignKeyConstraint(
            ["workspace_id", "import_mapping_id"],
            ["import_mappings.workspace_id", "import_mappings.id"],
            ondelete="SET NULL",
            name="fk_imports_workspace_mapping",
        ),
        # Abilita la FK composita da `transactions.import_id`.
        UniqueConstraint("workspace_id", "id", name="uq_imports_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # Identita' con cui il worker imposta app.current_user_id (nessuna
    # richiesta HTTP/JWT disponibile nel job) — vedi app/db/rls.py e
    # app/worker/jobs/import_csv.py. Utile anche per l'audit di SPEC §59.
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    import_mapping_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Snapshot immutabile della mappatura usata per il parsing (vedi
    # migration 0004): indipendente da import_mapping_id, che punta invece a
    # una mappatura riusabile salvata (opzionale).
    mapping_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # id del job arq: diagnostica e cancellazione (POST /imports/{id}/cancel).
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'uploaded'"))
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    transactions_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    transactions_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

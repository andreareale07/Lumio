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
# `classifying` resta nel CHECK constraint (la SPEC lo richiede) ma e'
# deliberatamente irraggiungibile: nessuna classificazione sincrona blocca
# piu' l'import (vedi ai_classification_job.py, disaccoppiato). `ready_for_
# review` invece E' raggiungibile da migration 0033 (Transaction
# Deduplication Engine, docs/SPEC_DEDUP_TRANSACTION.md): un import vi
# transita quando il dedup batch produce almeno una riga REVIEW ancora
# pendente, e ne esce solo quando l'utente ha deciso tutte le voci
# (`transaction_review_items.status='pending'` a zero per l'import).
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
# Milestone 05: secondo canale oltre al CSV di M04. Default 'csv' per le
# righe gia' esistenti (nessun backfill esplicito necessario).
FILE_TYPES = ("csv", "pdf")
# Classificazione AI disaccoppiata dal job di import (vedi migration 0019):
# None = import ancora in corso o creato prima di questa feature; "skipped"
# = nessuna AI attiva o nessuna transazione da classificare dopo le regole.
AI_CLASSIFICATION_STATUSES = ("pending", "running", "completed", "failed", "skipped")


class Import(Base):
    __tablename__ = "imports"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in IMPORT_STATUSES) + ")",
            name="ck_imports_status",
        ),
        CheckConstraint(
            "file_type IN (" + ", ".join(f"'{t}'" for t in FILE_TYPES) + ")",
            name="ck_imports_file_type",
        ),
        CheckConstraint(
            "ai_classification_status IN ("
            + ", ".join(f"'{s}'" for s in AI_CLASSIFICATION_STATUSES)
            + ") OR ai_classification_status IS NULL",
            name="ck_imports_ai_classification_status",
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
    # Nullable: il conto si sceglie/conferma DOPO l'upload (vedi migration
    # 0038 e `POST /imports/{id}/resolve-account`), non piu' prima di
    # caricare il file. Una riga in stato 'uploaded' puo' quindi esistere
    # per un breve periodo senza conto ancora assegnato.
    financial_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
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
    # una mappatura riusabile salvata (opzionale). Ha senso solo per
    # file_type='csv' — per 'pdf' il parser e' deterministico, nessuna
    # mappatura da scegliere.
    mapping_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Milestone 05: 'csv' (default, M04) o 'pdf'. bank_id/bank_parser_id sono
    # valorizzati insieme, solo quando file_type='pdf' (rilevati all'upload
    # da app.parsers.detect_parser) — vedi migration 0005.
    file_type: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'csv'"))
    bank_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("banks.id"), nullable=True
    )
    bank_parser_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_parsers.id"), nullable=True
    )
    # id del job arq: diagnostica e cancellazione (POST /imports/{id}/cancel).
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'uploaded'"))
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    transactions_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Transaction Deduplication Engine (migration 0033): transactions_imported
    # conta SOLO le righe realmente persistite come Transaction (NEW +
    # risolte come 'confirmed_distinct'), non piu' incondizionatamente
    # len(rows) — le due nuove colonne sotto coprono gli altri due esiti.
    transactions_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    transactions_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    transactions_review_pending: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_classification_status: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_transactions_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ai_transactions_classified: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Popolato SOLO quando ai_classification_status='failed' (stesso ruolo di
    # `error_message` sopra, ma per il job di classificazione AI separato —
    # vedi worker/jobs/ai_classification_job.py). Gap UX reale scoperto
    # testando un'interruzione del provider (container Ollama spento a meta'
    # import): il job transitava correttamente a 'failed', ma l'utente non
    # aveva modo di saperlo ne' perche' — l'indicatore di progresso "x/N"
    # spariva silenziosamente dalla UI senza alcun messaggio.
    ai_classification_error_message: Mapped[str | None] = mapped_column(String, nullable=True)

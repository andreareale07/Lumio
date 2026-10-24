import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

AI_RUN_KINDS = ("import_classification", "reclassification")
AI_EVENT_SEVERITIES = ("error", "warning", "info")


class AIRunEvent(Base):
    """Registro persistente di cio' che il motore AI di classificazione fa e
    dei suoi malfunzionamenti — prima finiva solo nel log del worker, che
    l'utente non vede mai: un provider spento, un'AI saltata perche' manca un
    profilo attivo, un job interrotto restavano invisibili.

    Non e' un log completo riga per riga (un import grande produrrebbe
    migliaia di righe): registra errori (con un tetto per esecuzione), il
    motivo per cui l'AI NON e' partita e un riepilogo a fine esecuzione.
    Il testo non contiene mai segreti (vedi
    `app/services/ai_run_event_service.py::describe_provider_error`)."""

    __tablename__ = "ai_run_events"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "run_kind IN (" + ", ".join(f"'{k}'" for k in AI_RUN_KINDS) + ")", name="ck_ai_run_events_run_kind"
        ),
        CheckConstraint(
            "severity IN (" + ", ".join(f"'{s}'" for s in AI_EVENT_SEVERITIES) + ")",
            name="ck_ai_run_events_severity",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "import_id"],
            ["imports.workspace_id", "imports.id"],
            ondelete="CASCADE",
            name="fk_ai_run_events_workspace_import",
        ),
        Index("ix_ai_run_events_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    run_kind: Mapped[str] = mapped_column(String, nullable=False)
    import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    # Codice stabile (es. "provider_error", "skipped_no_profile"): la UI lo
    # traduce, il backend non restituisce testo in nessuna lingua.
    code: Mapped[str] = mapped_column(String, nullable=False)
    # Dettaglio tecnico neutro rispetto alla lingua (es. "ConnectError (HTTP
    # 401)", oppure coppie "classified=12 no_match=3"): mai testo per l'utente.
    message: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

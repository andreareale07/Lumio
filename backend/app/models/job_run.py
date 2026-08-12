import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Elenco chiuso e volutamente piccolo: aggiungere un job futuro (es. un
# terzo provider, un export schedulato) significa solo aggiungere il suo
# nome qui e al CHECK della migration — la tabella/servizio (vedi
# app/services/job_run_tracker.py) sono gia' generici.
JOB_KINDS = ("market_data_refresh", "snapshot_rebuild", "google_sheets_export")
JOB_RUN_STATUSES = ("running", "success", "failed")


class JobRun(Base):
    """Stato minimo persistente dell'ULTIMA esecuzione di un job async
    innescabile manualmente (refresh prezzi, ricalcolo snapshot) o dal cron.

    Una sola riga per (workspace, job_kind), sovrascritta a ogni esecuzione
    (mai uno storico completo): l'utente deve solo sapere se/quando l'ultima
    esecuzione e' andata a buon fine, non consultare un log — a differenza
    di `ImportMapping`/`AIProfile` (profili di CONFIGURAZIONE, quelli
    restano sempre a lista con attivazione esplicita), questa e' l'unica
    istantanea di stato OPERATIVO, non una scelta di prodotto da preservare."""

    __tablename__ = "job_runs"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "job_kind IN (" + ", ".join(f"'{k}'" for k in JOB_KINDS) + ")",
            name="ck_job_runs_job_kind",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in JOB_RUN_STATUSES) + ")",
            name="ck_job_runs_status",
        ),
        UniqueConstraint("workspace_id", "job_kind", name="uq_job_runs_workspace_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    # id del job arq: solo diagnostica lato server, mai esposto in API/UI
    # (nessun ID tecnico in vista, vedi brief del gap UX).
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)

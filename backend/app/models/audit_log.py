import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Elenco chiuso (SPEC §59): un evento nuovo richiede di aggiungerlo qui E al
# CHECK della migration, stesso pattern di JOB_KINDS in app/models/job_run.py.
EVENT_TYPES = (
    "LOGIN",
    "IMPORT_CREATED",
    "IMPORT_COMPLETED",
    "TRANSACTION_UPDATED",
    "CATEGORY_CHANGED",
    "RULE_CREATED",
    "RULE_UPDATED",
    "AI_PROVIDER_CHANGED",
    "GOOGLE_CONNECTED",
    "EXPORT_CREATED",
    "IMPORT_DELETED",
)


class AuditLog(Base):
    """Registro append-only delle azioni rilevanti (SPEC §59, milestone 11).

    A differenza di ogni altra tabella RLS del progetto, qui esistono
    SOLO le policy SELECT/INSERT (migration 0017) — nessuna UPDATE/DELETE:
    un log di audit non deve essere alterabile nemmeno da chi lo ha generato.

    Nessuna UI di consultazione in questa milestone (deciso con l'utente in
    fase di piano) — il modello e' pero' gia' pensato per la futura
    schermata "Impostazioni istanza" (solo ruolo admin): RLS standard
    workspace-scoped, cosi' quella pagina potra' limitarsi a un SELECT.
    """

    __tablename__ = "audit_log"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL (non CASCADE): un utente puo' in futuro essere rimosso senza
    # far sparire le righe di audit che lo riguardano — solo l'attore
    # diventa "sconosciuto", l'evento resta.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Attributo Python diverso dal nome colonna DB ("metadata" collide con
    # Base.metadata a livello di classe SQLAlchemy).
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

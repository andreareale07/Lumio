import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

AI_PROVIDERS = ("ollama", "openai", "anthropic", "custom")


class AIProfile(Base):
    """Milestone 07 — configurazione AI salvata per workspace (SPEC §25-28).

    Piu' righe per workspace (a differenza della prima versione di questa
    milestone, che ne ammetteva una sola): un utente puo' salvare piu'
    profili anche dello stesso provider (es. due endpoint Ollama diversi) e
    passare dall'uno all'altro senza perdere le configurazioni non attive —
    richiesto esplicitamente durante la revisione di questa milestone.

    Al massimo UN profilo per workspace ha `is_active=true`
    (`uq_ai_profiles_one_active_per_workspace`, indice UNIQUE parziale —
    mutua esclusivita' garantita a livello DB, non solo applicativo).
    Nessun profilo attivo = AI disabilitata per il workspace (SPEC §25,
    "l'app deve funzionare completamente anche con AI disabled"): non
    esiste un profilo "none" a se stante, l'assenza di un attivo e' di per
    se' lo stato "disabilitata".

    `provider` e' immutabile dopo la creazione (nessun UPDATE lo modifica,
    vedi `app/services/ai_profile_service.py`): cambiare provider significa
    creare un nuovo profilo, mai convertirne uno esistente — evita che una
    API key resti agganciata a un provider per cui non ha piu' senso.

    `api_key_encrypted` e' sempre cifrato a riposo (Fernet,
    `app/core/crypto.py`) e non viene mai restituito in chiaro dall'API
    (SPEC §27): le response espongono solo `api_key_set: bool`.
    """

    __tablename__ = "ai_profiles"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "provider IN ('ollama', 'openai', 'anthropic', 'custom')",
            name="ck_ai_profiles_provider",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

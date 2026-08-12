import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleIntegration(Base):
    """Milestone 10 — integrazione Google Sheets (SPEC §47/48/50/51/54).

    Una sola riga per workspace (`UniqueConstraint(workspace_id)`), non una
    lista di profili come `AIProfile`/`MarketDataProfile`: qui non si
    confrontano provider intercambiabili, si collega un unico account
    Google personale (coerente col mockup SPEC_FE, una card
    Connect/Connected, mai una lista tra cui scegliere).

    `credentials_encrypted` e' un blob JSON cifrato (Fernet, vedi
    `app/core/crypto.py`) con `access_token`/`refresh_token`/`expires_at`/
    `scope` — una stringa unica invece di colonne separate: aggiornamento
    atomico ad ogni refresh (l'access token cambia spesso, il refresh token
    quasi mai) senza rischiare scritture parziali, e nessuna migration
    aggiuntiva se in futuro serve conservare anche altro (es. `id_token`).

    `spreadsheet_id`/`spreadsheet_url` sono l'UNICO file gestito da Lumio
    per questo workspace (creato automaticamente al connect, mai una scelta
    tra file esistenti — scope OAuth `drive.file`: Lumio puo' vedere/
    scrivere solo file che ha creato lei stessa).

    `default_drive_folder_id`/`_name` sono opzionali (NULL = root "Il mio
    Drive"): scelti dall'utente via Google Picker al connect, riproposti
    come default ad ogni export ma sempre modificabili (mai un path
    testuale libero, vedi frontend `DriveFolderPicker`).
    """

    __tablename__ = "google_integrations"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_google_integrations_workspace"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    google_account_email: Mapped[str] = mapped_column(String, nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(String, nullable=False)
    spreadsheet_id: Mapped[str] = mapped_column(String, nullable=False)
    spreadsheet_url: Mapped[str] = mapped_column(String, nullable=False)
    default_drive_folder_id: Mapped[str | None] = mapped_column(String, nullable=True)
    default_drive_folder_name: Mapped[str | None] = mapped_column(String, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

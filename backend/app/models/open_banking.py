import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PROVIDERS = ("enable_banking",)
CONNECTION_STATUSES = ("pending", "active", "expired", "revoked", "error")


class OpenBankingCredential(Base):
    """Application ID + chiave privata RSA dell'app Enable Banking di UN utente.

    I Terms di Enable Banking (2026-01-09) consentono la produzione gratuita
    solo per uso personale di persone fisiche con conti propri, e vietano di
    rendere accessibile l'API a terzi: le credenziali quindi sono per utente e
    la RLS e' owner-only (piu' stretta del solito `is_workspace_member`), mai
    visibili agli altri membri del workspace. La chiave e' generata da Lumio e
    non esce mai dal server; `certificate_pem` e' la parte pubblica, da
    caricare sul Control Panel del provider.
    """

    __tablename__ = "open_banking_credentials"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("provider IN ('enable_banking')", name="ck_open_banking_credentials_provider"),
        UniqueConstraint("owner_user_id", "provider", name="uq_open_banking_credentials_owner_provider"),
        UniqueConstraint("workspace_id", "id", name="uq_open_banking_credentials_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    # NULL finche' l'utente non ha registrato l'app sul Control Panel e
    # incollato l'ID ricevuto.
    application_id: Mapped[str | None] = mapped_column(String, nullable=True)
    private_key_encrypted: Mapped[str] = mapped_column(String, nullable=False)
    certificate_pem: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BankConnection(Base):
    """Una banca collegata (una sessione di consenso presso il provider)."""

    __tablename__ = "bank_connections"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in CONNECTION_STATUSES) + ")",
            name="ck_bank_connections_status",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["open_banking_credentials.workspace_id", "open_banking_credentials.id"],
            ondelete="CASCADE",
            name="fk_bank_connections_workspace_credential",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_bank_connections_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    aspsp_name: Mapped[str] = mapped_column(String, nullable=False)
    aspsp_country: Mapped[str] = mapped_column(String(2), nullable=False)
    psu_type: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'personal'"))
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    # Hash SHA-256 del nonce contenuto nello `state` OAuth: monouso, azzerato
    # quando il callback lo consuma (un `state` rigiocato non trova nulla).
    state_nonce_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authorization_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Cifrato (Fernet): e' l'unico segreto che permette di leggere i conti.
    session_id_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Solo un codice/messaggio generico, mai dati finanziari (SPEC §55).
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BankConnectionAccount(Base):
    """Conto esposto da una connessione, opzionalmente abbinato a un conto Lumio."""

    __tablename__ = "bank_connection_accounts"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["bank_connections.workspace_id", "bank_connections.id"],
            ondelete="CASCADE",
            name="fk_bank_connection_accounts_workspace_connection",
        ),
        UniqueConstraint("connection_id", "provider_account_uid", name="uq_bank_connection_accounts_uid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Identificativo del conto valido solo finche' la sessione e' attiva.
    provider_account_uid: Mapped[str] = mapped_column(String, nullable=False)
    iban: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    product: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    cash_account_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # FK composita verso financial_accounts con SET NULL sulla sola colonna
    # financial_account_id: definita solo in migration 0044 (la sintassi con
    # elenco colonne non e' esprimibile qui).
    financial_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Cursore di sync incrementale: ultima data contabile importata.
    last_booked_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transactions_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

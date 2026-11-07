import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_APPLICATION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,100}$")


class CredentialOut(BaseModel):
    provider: str
    # `False` finche' l'utente non ha incollato l'application ID ricevuto dal
    # Control Panel del provider (passo 2 della procedura guidata).
    configured: bool
    application_id: str | None
    # Parte PUBBLICA da caricare sul Control Panel. La chiave privata non e'
    # mai restituita da nessun endpoint.
    certificate_pem: str
    created_at: datetime


class OpenBankingStatusOut(BaseModel):
    redirect_uri: str
    redirect_uri_configured: bool
    credential: CredentialOut | None


class ApplicationIdIn(BaseModel):
    application_id: str

    @field_validator("application_id")
    @classmethod
    def _validate(cls, value: str) -> str:
        value = value.strip()
        if not _APPLICATION_ID_RE.match(value):
            raise ValueError("Application ID non valido")
        return value


class InstitutionOut(BaseModel):
    name: str
    country: str
    logo_url: str | None
    beta: bool
    maximum_consent_validity_days: int | None


class StartConnectionIn(BaseModel):
    aspsp_name: str = Field(min_length=1, max_length=200)
    aspsp_country: str = Field(min_length=2, max_length=2)
    # Solo conti di persone fisiche: i Terms del provider escludono l'uso
    # per conti aziendali sul piano gratuito.
    psu_type: Literal["personal"] = "personal"


class ConnectUrlOut(BaseModel):
    authorize_url: str


class ConnectionAccountOut(BaseModel):
    id: uuid.UUID
    name: str | None
    product: str | None
    iban_masked: str | None
    currency: str | None
    enabled: bool
    financial_account_id: uuid.UUID | None
    last_sync_at: datetime | None
    transactions_imported: int


class ConnectionOut(BaseModel):
    id: uuid.UUID
    aspsp_name: str
    aspsp_country: str
    status: str
    valid_until: datetime | None
    days_until_expiry: int | None
    # True quando mancano meno di 7 giorni alla scadenza del consenso: la UI
    # propone il rinnovo prima che la sincronizzazione smetta di funzionare.
    expiring_soon: bool
    last_sync_at: datetime | None
    last_error: str | None
    sync_running: bool
    accounts: list[ConnectionAccountOut]


class AccountUpdateIn(BaseModel):
    enabled: bool | None = None
    # Abbina a un conto Lumio esistente...
    financial_account_id: uuid.UUID | None = None
    # ...oppure crea al volo un conto Lumio coi dati del conto bancario.
    create_account: bool = False


class SyncQueuedOut(BaseModel):
    status: Literal["queued"] = "queued"


class DisconnectResultOut(BaseModel):
    # Movimenti eliminati: 0 se l'utente non ha chiesto di eliminare i dati.
    deleted_transactions: int
    # False se la revoca presso la banca non e' riuscita: lo scollegamento locale
    # e' comunque avvenuto e il consenso scade da solo.
    revoked_at_bank: bool

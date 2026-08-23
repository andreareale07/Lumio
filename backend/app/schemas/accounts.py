import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.financial_account import ACCOUNT_TYPES, CLASSIFICATION_LANGUAGES

# Nessun controllo di checksum IBAN (fuori scope, milestone 09.5b): solo una
# sanity-check di lunghezza/charset, sufficiente a evitare un valore
# palesemente sbagliato. Normalizzato (maiuscolo, senza spazi) qui — unico
# punto server-side, cosi' il confronto in app/services/transfer_recognition.py
# non deve normalizzare due volte lo stesso formato in modi diversi.
_IBAN_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


def _normalize_iban(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper().replace(" ", "")
    if not normalized:
        return None
    if not _IBAN_PATTERN.match(normalized):
        raise ValueError("IBAN non valido")
    return normalized


class FinancialAccountCreate(BaseModel):
    bank_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    account_type: str = Field(pattern="^(" + "|".join(ACCOUNT_TYPES) + ")$")
    currency: str = Field(min_length=3, max_length=3)
    account_identifier_masked: str | None = None
    iban: str | None = None
    classification_language: str | None = Field(default=None, pattern="^(" + "|".join(CLASSIFICATION_LANGUAGES) + ")$")

    @field_validator("iban")
    @classmethod
    def _validate_iban(cls, v: str | None) -> str | None:
        return _normalize_iban(v)


class FinancialAccountUpdate(BaseModel):
    bank_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    account_type: str | None = Field(default=None, pattern="^(" + "|".join(ACCOUNT_TYPES) + ")$")
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    account_identifier_masked: str | None = None
    iban: str | None = None
    classification_language: str | None = Field(default=None, pattern="^(" + "|".join(CLASSIFICATION_LANGUAGES) + ")$")
    is_active: bool | None = None

    @field_validator("iban")
    @classmethod
    def _validate_iban(cls, v: str | None) -> str | None:
        return _normalize_iban(v)


class FinancialAccountOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    bank_id: uuid.UUID | None
    name: str
    account_type: str
    currency: str
    account_identifier_masked: str | None
    iban: str | None
    classification_language: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IbanHistoryCreate(BaseModel):
    """Milestone 09.5c: aggiunta MANUALE di un IBAN storico del conto — a
    differenza della storicizzazione automatica (che scatta solo quando il
    campo IBAN cambia in `PATCH /accounts/{id}`), questa serve per chi
    imposta un conto per la prima volta conoscendo GIA' sia l'IBAN attuale
    sia uno precedente (es. un istituto che ha cambiato IBAN prima ancora
    che l'utente iniziasse a usare Lumio)."""

    iban: str = Field(min_length=1)

    @field_validator("iban")
    @classmethod
    def _validate_iban(cls, v: str) -> str:
        normalized = _normalize_iban(v)
        if normalized is None:
            raise ValueError("IBAN non valido")
        return normalized


class IbanHistoryOut(BaseModel):
    id: uuid.UUID
    iban: str
    created_at: datetime

    model_config = {"from_attributes": True}

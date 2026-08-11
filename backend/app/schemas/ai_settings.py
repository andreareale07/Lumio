import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AIProvider = Literal["ollama", "openai", "anthropic", "custom"]


class AIProfileCreate(BaseModel):
    name: str
    provider: AIProvider
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None


class AIProfileUpdate(BaseModel):
    """`provider` non e' modificabile (vedi `app/models/ai_profile.py`):
    cambiarlo richiede creare un nuovo profilo. `api_key`: `None` = mantieni
    la chiave gia' salvata, stringa vuota = rimuovila, stringa non vuota =
    sostituiscila."""

    name: str | None = None
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None


class AIProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    provider: AIProvider
    endpoint: str | None
    model: str | None
    api_key_set: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AIConnectionCheckRequest(BaseModel):
    """Payload di `POST /settings/ai/test` e `/settings/ai/models` per un
    profilo NON ANCORA salvato (l'utente vuole verificarlo prima di
    crearlo). Per un profilo gia' salvato si usano invece
    `/settings/ai/profiles/{id}/test` e `.../models`, senza payload — usano
    la configurazione gia' persistita."""

    provider: AIProvider
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None


class AITestConnectionResult(BaseModel):
    success: bool
    message: str


class AIModelListResult(BaseModel):
    success: bool
    models: list[str]
    message: str

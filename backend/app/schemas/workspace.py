import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    base_currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceUpdate(BaseModel):
    # Solo `base_currency` per ora (sistema di valute) — cambiarla non
    # riconverte nulla di storico, e' solo la valuta di visualizzazione/
    # aggregazione da quel momento (vedi app/services/analytics.py).
    base_currency: str = Field(min_length=3, max_length=10)

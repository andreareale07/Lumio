import uuid
from datetime import datetime

from pydantic import BaseModel


class AIEngineProfileOut(BaseModel):
    name: str
    provider: str
    model: str | None


class AIEngineImportOut(BaseModel):
    import_id: uuid.UUID
    filename: str
    completed_at: datetime | None
    # None per gli import precedenti all'introduzione del job AI separato.
    ai_status: str | None
    ai_total: int
    ai_classified: int
    ai_error_message: str | None
    # Transazioni di questo import ancora senza categoria e idonee all'AI.
    uncategorized_eligible: int
    # Il rilancio e' offerto solo se ha senso: import completato, AI non in
    # corso, e un profilo attivo con qualcosa da classificare.
    can_retry: bool


class AIEngineStatusOut(BaseModel):
    active_profile: AIEngineProfileOut | None
    uncategorized_eligible: int
    errors_last_24h: int
    last_error_at: datetime | None
    recent_imports: list[AIEngineImportOut]


class AIRunEventOut(BaseModel):
    id: uuid.UUID
    run_kind: str
    import_id: uuid.UUID | None
    import_filename: str | None
    severity: str
    code: str
    message: str
    created_at: datetime


class AIRunEventListOut(BaseModel):
    items: list[AIRunEventOut]
    total: int


class AIRetryResultOut(BaseModel):
    ai_status: str | None
    ai_total: int

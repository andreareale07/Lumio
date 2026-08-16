import uuid
from typing import Literal

from pydantic import BaseModel, Field

# Tenuto in sincrono manualmente con app.models.category.CATEGORY_KINDS
# (verificato da tests/test_categories.py) — un Literal non puo' essere
# costruito da una tupla a runtime senza perdere l'autocompletamento statico.
CategoryKind = Literal["expense", "income", "transfer", "investment", "neutral"]


class CategoryCreate(BaseModel):
    parent_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    # `code` NON e' piu' un campo di input (rework tassonomia): generato
    # server-side da `category_service.generate_code` — prefisso del padre
    # + slug, con suffisso anti-collisione. Un client non aggiornato che
    # invia ancora `code` non causa errori: Pydantic scarta i campi extra
    # per default.
    kind: CategoryKind | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    parent_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: CategoryKind | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    name: str
    code: str
    kind: CategoryKind
    is_system: bool
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}

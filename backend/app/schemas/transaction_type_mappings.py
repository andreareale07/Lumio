from pydantic import BaseModel, Field

from app.models.transaction import TRANSACTION_TYPES

_TYPE_PATTERN = "^(" + "|".join(TRANSACTION_TYPES) + ")$"


class TypeCountOut(BaseModel):
    transaction_type: str
    count: int


class LabelOut(BaseModel):
    source_type_raw: str
    total_count: int
    # Puo' avere piu' di una riga: il default del parser per la stessa
    # etichetta puo' variare per direzione (es. "Transazione con carta").
    current_types: list[TypeCountOut]
    override: str | None


class MappingUpsert(BaseModel):
    transaction_type: str = Field(pattern=_TYPE_PATTERN)


class ReapplyResultOut(BaseModel):
    updated: int
    skipped: int


class MappingUpsertResult(BaseModel):
    source_type_raw: str
    transaction_type: str
    reapply: ReapplyResultOut

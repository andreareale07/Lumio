import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

RuleField = Literal["description", "merchant"]
RuleOperator = Literal["equals", "contains", "starts_with", "ends_with", "regex", "merchant_equals"]


def _validate_regex(operator: str | None, value: str | None) -> None:
    if operator == "regex" and value is not None:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex pattern: {exc}") from exc


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    field: RuleField
    operator: RuleOperator
    value: str = Field(min_length=1)
    category_id: uuid.UUID
    priority: int = 100
    is_active: bool = True

    @field_validator("value")
    @classmethod
    def _value_is_valid_regex_if_needed(cls, v: str, info) -> str:
        _validate_regex(info.data.get("operator"), v)
        return v

    @model_validator(mode="after")
    def _merchant_equals_requires_merchant_field(self) -> "RuleCreate":
        if self.operator == "merchant_equals" and self.field != "merchant":
            raise ValueError("operator 'merchant_equals' richiede field='merchant'")
        return self


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    field: RuleField | None = None
    operator: RuleOperator | None = None
    value: str | None = Field(default=None, min_length=1)
    category_id: uuid.UUID | None = None
    priority: int | None = None
    is_active: bool | None = None

    # Validazione incrociata solo sui campi presenti in questo payload: un
    # update parziale che cambia solo `value` su una regola regex esistente
    # non ha qui il contesto per rivalidare l'intera regola risultante (non
    # ricarica la riga dal DB) — stesso livello di validazione parziale gia'
    # accettato per gli altri update in questo backend (es. CategoryUpdate).
    @model_validator(mode="after")
    def _cross_field_validation(self) -> "RuleUpdate":
        _validate_regex(self.operator, self.value)
        if self.operator == "merchant_equals" and self.field is not None and self.field != "merchant":
            raise ValueError("operator 'merchant_equals' richiede field='merchant'")
        return self


class RuleOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    field: RuleField
    operator: RuleOperator
    value: str
    category_id: uuid.UUID
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleSuggestion(BaseModel):
    """Proposta di regola calcolata al volo dallo storico correzioni
    (SPEC §29), non persistita — vedi decisione documentata nel piano di M06.
    """

    match_field: RuleField
    match_value: str
    category_id: uuid.UUID
    occurrences: int
    transaction_ids: list[uuid.UUID]

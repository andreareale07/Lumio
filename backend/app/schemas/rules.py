import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.services.rules_engine import check_regex_safety

RuleField = Literal["description", "merchant"]
RuleOperator = Literal["equals", "contains", "starts_with", "ends_with", "regex", "merchant_equals"]
MatchMode = Literal["all", "any"]

MAX_CONDITIONS = 10


class TextCondition(BaseModel):
    field: RuleField
    operator: RuleOperator
    value: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _validate(self) -> "TextCondition":
        if self.operator == "regex":
            check_regex_safety(self.value)
        if self.operator == "merchant_equals" and self.field != "merchant":
            raise ValueError("operator 'merchant_equals' richiede field='merchant'")
        return self


class AmountCondition(BaseModel):
    """Importo tra `min` e `max` sul valore assoluto; almeno un estremo."""

    field: Literal["amount"]
    operator: Literal["between"] = "between"
    min: Decimal | None = Field(default=None, ge=0)
    max: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate(self) -> "AmountCondition":
        if self.min is None and self.max is None:
            raise ValueError("la condizione sull'importo richiede almeno un estremo")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("l'importo minimo supera il massimo")
        return self


RuleCondition = Annotated[TextCondition | AmountCondition, Field(discriminator="field")]


def _legacy_to_conditions(data: Any) -> Any:
    """Forma abbreviata a una sola condizione (`field`/`operator`/`value`):
    la usano i client che non conoscono ancora `conditions`."""
    if isinstance(data, dict) and "conditions" not in data and {"field", "operator", "value"} <= data.keys():
        data = dict(data)
        data["conditions"] = [
            {"field": data.pop("field"), "operator": data.pop("operator"), "value": data.pop("value")}
        ]
    return data


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    conditions: list[RuleCondition] = Field(min_length=1, max_length=MAX_CONDITIONS)
    match_mode: MatchMode = "all"
    category_id: uuid.UUID
    priority: int = 100
    is_active: bool = True

    @model_validator(mode="before")
    @classmethod
    def _accept_single_condition_shorthand(cls, data: Any) -> Any:
        return _legacy_to_conditions(data)


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    conditions: list[RuleCondition] | None = Field(default=None, min_length=1, max_length=MAX_CONDITIONS)
    match_mode: MatchMode | None = None
    category_id: uuid.UUID | None = None
    priority: int | None = None
    is_active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_single_condition_shorthand(cls, data: Any) -> Any:
        return _legacy_to_conditions(data)


class RuleOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    conditions: list[RuleCondition]
    match_mode: MatchMode
    category_id: uuid.UUID
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RulePreviewRequest(BaseModel):
    """Regola non salvata di cui si vuole vedere l'impatto."""

    conditions: list[RuleCondition] = Field(min_length=1, max_length=MAX_CONDITIONS)
    match_mode: MatchMode = "all"
    category_id: uuid.UUID
    group: Literal["change", "ok", "protected"] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _accept_single_condition_shorthand(cls, data: Any) -> Any:
        return _legacy_to_conditions(data)


class RulePreviewItem(BaseModel):
    id: uuid.UUID
    date: str
    amount: Decimal
    currency: str
    description: str
    category_id: uuid.UUID | None
    group: Literal["change", "ok", "protected"]
    # Intervalli [inizio, fine) della `description` che hanno fatto scattare
    # le condizioni di testo, gia' calcolati con la semantica del motore.
    spans: list[tuple[int, int]]


class RulePreviewOut(BaseModel):
    would_change: int
    already_correct: int
    protected: int
    recategorized: int
    total: int
    group: Literal["change", "ok", "protected"] | None
    items: list[RulePreviewItem]
    truncated: bool = False


class SuggestionOption(BaseModel):
    """Una delle proposte di una suggestion, dalla piu' precisa alla piu' ampia."""

    key: Literal["precise", "recommended", "broad"]
    conditions: list[RuleCondition]
    match_mode: MatchMode = "all"
    would_change: int
    already_correct: int
    protected: int


class RuleSuggestion(BaseModel):
    """Proposta di regola calcolata al volo dallo storico correzioni
    (SPEC §29), non persistita — vedi decisione documentata nel piano di M06.
    """

    category_id: uuid.UUID
    occurrences: int
    transaction_ids: list[uuid.UUID]
    # Etichetta breve per la card (la frase stabile piu' rappresentativa).
    label: str
    # Il testo da solo non distingue le categorie scelte: altri movimenti con
    # la stessa frase portano a una categoria diversa.
    ambiguous: bool = False
    options: list[SuggestionOption]

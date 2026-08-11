import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.financial_account import ACCOUNT_TYPES


class FinancialAccountCreate(BaseModel):
    bank_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    account_type: str = Field(pattern="^(" + "|".join(ACCOUNT_TYPES) + ")$")
    currency: str = Field(min_length=3, max_length=3)
    account_identifier_masked: str | None = None
    iban: str | None = None


class FinancialAccountUpdate(BaseModel):
    bank_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    account_type: str | None = Field(default=None, pattern="^(" + "|".join(ACCOUNT_TYPES) + ")$")
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    account_identifier_masked: str | None = None
    iban: str | None = None
    is_active: bool | None = None


class FinancialAccountOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    bank_id: uuid.UUID | None
    name: str
    account_type: str
    currency: str
    account_identifier_masked: str | None
    iban: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

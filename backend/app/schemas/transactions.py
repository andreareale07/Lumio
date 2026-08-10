import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.classification import CLASSIFICATION_METHODS
from app.models.transaction import DIRECTIONS, STATUSES, TRANSACTION_TYPES


class TransactionCreate(BaseModel):
    financial_account_id: uuid.UUID
    category_id: uuid.UUID | None = None
    transaction_date: date
    value_date: date | None = None
    description_raw: str = Field(min_length=1)
    merchant: str | None = None
    reference: str | None = None
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    direction: str = Field(pattern="^(" + "|".join(DIRECTIONS) + ")$")
    transaction_type: str = Field(pattern="^(" + "|".join(TRANSACTION_TYPES) + ")$")
    balance_after: Decimal | None = None
    status: str = Field(default="confirmed", pattern="^(" + "|".join(STATUSES) + ")$")


class TransactionUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    transaction_date: date | None = None
    value_date: date | None = None
    description_normalized: str | None = None
    merchant: str | None = None
    reference: str | None = None
    transaction_type: str | None = Field(
        default=None, pattern="^(" + "|".join(TRANSACTION_TYPES) + ")$"
    )
    status: str | None = Field(default=None, pattern="^(" + "|".join(STATUSES) + ")$")


class TransactionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    financial_account_id: uuid.UUID
    import_id: uuid.UUID | None
    category_id: uuid.UUID | None
    transaction_date: date
    value_date: date | None
    description_raw: str
    description_normalized: str | None
    merchant: str | None
    reference: str | None
    amount: Decimal
    currency: str
    direction: str
    transaction_type: str
    balance_after: Decimal | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClassificationOut(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    method: str = Field(pattern="^(" + "|".join(CLASSIFICATION_METHODS) + ")$")
    provider: str | None
    model: str | None
    category_id: uuid.UUID | None
    score: Decimal | None
    explanation: str | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}

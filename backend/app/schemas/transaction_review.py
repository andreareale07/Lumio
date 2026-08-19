import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

DUPLICATE_REVIEW_DECISIONS = ("keep_new", "mark_duplicate")


class DuplicateReviewCandidateOut(BaseModel):
    """Il record 'gia' presente' mostrato a confronto (SPEC §15) — sottoinsieme
    dei campi di Transaction rilevanti per il confronto visivo."""

    id: uuid.UUID
    transaction_date: date
    description_raw: str
    description_normalized: str | None
    amount: Decimal
    currency: str
    transaction_type: str
    balance_after: Decimal | None

    model_config = {"from_attributes": True}


class DuplicateReviewItemOut(BaseModel):
    id: uuid.UUID
    import_id: uuid.UUID
    financial_account_id: uuid.UUID
    row_index: int
    transaction_date: date
    description_raw: str
    description_normalized: str | None
    amount: Decimal
    currency: str
    transaction_type: str
    balance_after: Decimal | None
    status: str
    auto_resolved: bool
    decided_at: datetime | None
    created_at: datetime
    candidate: DuplicateReviewCandidateOut | None

    model_config = {"from_attributes": True}


class DuplicateReviewSummaryOut(BaseModel):
    pending: int
    confirmed_new: int
    confirmed_duplicate: int


class DuplicateReviewDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(" + "|".join(DUPLICATE_REVIEW_DECISIONS) + ")$")

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.models.investment_transaction import INVESTMENT_TRANSACTION_TYPES
from app.schemas.decimal_fields import format_fixed_decimal_optional

_TYPE_PATTERN = "^(" + "|".join(INVESTMENT_TRANSACTION_TYPES) + ")$"


class InvestmentTransactionCreate(BaseModel):
    financial_account_id: uuid.UUID
    asset_id: uuid.UUID | None = None
    transaction_id: uuid.UUID | None = None
    trade_date: date
    type: str = Field(pattern=_TYPE_PATTERN)
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal
    fees: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    currency: str = Field(min_length=3, max_length=3)
    notes: str | None = None
    # `source_type_raw` NON e' accettato dall'API: e' provenienza di parser
    # (rimandata a un'integrazione futura), un inserimento manuale non ha
    # un'etichetta grezza da conservare.


class InvestmentTransactionUpdate(BaseModel):
    asset_id: uuid.UUID | None = None
    transaction_id: uuid.UUID | None = None
    trade_date: date | None = None
    type: str | None = Field(default=None, pattern=_TYPE_PATTERN)
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal | None = None
    fees: Decimal | None = None
    tax: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None


class InvestmentBackfillResult(BaseModel):
    """Risposta di `POST /investment-transactions/backfill` (milestone
    09c): quante transazioni 'investment' gia' importate sono state
    scansionate, quante hanno prodotto un movimento nuovo, quante erano gia'
    collegate (nessuna azione), quante non erano in un formato
    riconosciuto (nessun dato inventato)."""

    scanned: int
    created: int
    skipped_already_linked: int
    skipped_unrecognized: int


class InvestmentTransactionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    financial_account_id: uuid.UUID
    asset_id: uuid.UUID | None
    transaction_id: uuid.UUID | None
    trade_date: date
    type: str
    quantity: Decimal | None
    price: Decimal | None
    amount: Decimal
    fees: Decimal
    tax: Decimal
    currency: str
    source_type_raw: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    # Numeric(28, 10): stesso rischio di notazione scientifica per un
    # valore a zero esatto di PositionOut.quantity — vedi
    # app/schemas/decimal_fields.py.
    _serialize_quantity = field_serializer("quantity")(format_fixed_decimal_optional)

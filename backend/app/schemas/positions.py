import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.schemas.decimal_fields import format_fixed_decimal


class PositionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    financial_account_id: uuid.UUID
    asset_id: uuid.UUID
    quantity: Decimal
    average_cost: Decimal
    realized_pl: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    # Numeric(28, 10): una posizione chiusa esattamente puo' produrre un
    # Decimal zero in notazione scientifica ("0E-10") — vedi
    # app/schemas/decimal_fields.py per il perche'.
    _serialize_quantity = field_serializer("quantity")(format_fixed_decimal)


class PositionManualEdit(BaseModel):
    """SPEC/decisione M09: modifica manuale di una posizione. Non e' un
    PATCH diretto sui campi di `Position` — il backend traduce questi valori
    in un movimento `adjustment` (vedi `position_service.apply_manual_position_edit`),
    cosi' `investment_transactions` resta l'unica sorgente di verita'."""

    quantity: Decimal = Field(ge=0)
    average_cost: Decimal = Field(ge=0)
    notes: str | None = None

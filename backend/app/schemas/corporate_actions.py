import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.schemas.decimal_fields import format_fixed_decimal


class SplitSuggestionOut(BaseModel):
    source_asset_id: uuid.UUID
    target_asset_id: uuid.UUID
    source_label: str
    target_label: str
    source_quantity: Decimal
    target_quantity: Decimal
    # Unita' del titolo nuovo per 1 del vecchio (0.0001 = raggruppamento 10.000:1).
    ratio: Decimal
    split_date: date
    confidence: str  # "high" | "medium"
    quantity_matched: bool

    _serialize_ratio = field_serializer("ratio", "source_quantity", "target_quantity")(format_fixed_decimal)


class ExpirySuggestionOut(BaseModel):
    asset_id: uuid.UUID
    asset_label: str
    quantity: Decimal
    cost_basis: Decimal
    currency: str
    last_price_date: date | None

    _serialize_quantity = field_serializer("quantity")(format_fixed_decimal)


class CorporateActionSuggestionsOut(BaseModel):
    splits: list[SplitSuggestionOut]
    expirations: list[ExpirySuggestionOut]


class MergeAssetsRequest(BaseModel):
    source_asset_id: uuid.UUID
    target_asset_id: uuid.UUID
    ratio: Decimal = Field(gt=0)
    split_date: date | None = None


class ExpireAssetRequest(BaseModel):
    asset_id: uuid.UUID
    expiry_date: date


class ExpireAssetResult(BaseModel):
    closed_positions: int

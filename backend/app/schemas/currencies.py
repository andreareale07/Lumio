from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class CurrencyOut(BaseModel):
    code: str
    name: str
    symbol: str
    decimal_digits: int
    is_system: bool

    model_config = {"from_attributes": True}


class FxRateManualUpsert(BaseModel):
    from_currency: str = Field(min_length=3, max_length=10)
    to_currency: str = Field(min_length=3, max_length=10)
    rate_date: date
    rate: Decimal


class FxRateOut(BaseModel):
    from_currency: str
    to_currency: str
    rate_date: date
    rate: Decimal
    source: str

    model_config = {"from_attributes": True}

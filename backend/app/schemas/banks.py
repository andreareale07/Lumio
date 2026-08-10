import uuid

from pydantic import BaseModel


class BankOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    country: str | None

    model_config = {"from_attributes": True}

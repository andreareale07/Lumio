from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SystemSettingOut(BaseModel):
    key: str
    value: Any
    default_value: Any
    description: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class SystemSettingUpdate(BaseModel):
    value: Any

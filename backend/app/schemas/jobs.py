from typing import Any, Literal

from pydantic import BaseModel


class JobParameterOut(BaseModel):
    label: str
    unit: str
    editable: bool
    setting_key: str | None
    value: Any
    readonly_reason: str | None


class JobOut(BaseModel):
    kind: str
    category: Literal["scheduled", "triggered"]
    name: str
    description: str
    schedule_description: str | None
    disable_warning: str | None
    enabled: bool | None
    enabled_setting_key: str | None
    parameters: list[JobParameterOut]

from typing import Any, Literal

from pydantic import BaseModel


class JobParameterOut(BaseModel):
    label_key: str
    unit_key: str
    editable: bool
    setting_key: str | None
    value: Any
    readonly_reason_key: str | None


class JobOut(BaseModel):
    kind: str
    category: Literal["scheduled", "triggered"]
    name_key: str
    description_key: str
    schedule_description_key: str | None
    schedule_readonly_reason_key: str | None
    disable_warning_key: str | None
    enabled: bool | None
    enabled_setting_key: str | None
    parameters: list[JobParameterOut]

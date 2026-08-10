import uuid

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    parent_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=100)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    parent_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    sort_order: int | None = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    name: str
    code: str
    is_system: bool
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}

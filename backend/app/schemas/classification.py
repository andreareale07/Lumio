import uuid
from typing import Literal

from pydantic import BaseModel

ReclassificationScope = Literal["uncategorized", "all_except_manual"]


class ReclassifyRequest(BaseModel):
    scope: ReclassificationScope = "uncategorized"
    run_ai: bool = False
    # Se presente, il job agisce solo sui movimenti che combaciano con questa
    # regola (applica una regola appena creata ai movimenti esistenti).
    rule_id: uuid.UUID | None = None


class ReclassifyTriggered(BaseModel):
    job_id: str


class CategoryPreviewBreakdownOut(BaseModel):
    category_id: uuid.UUID
    category_code: str
    category_name: str
    count: int
    examples: list[str]


class ReclassificationPreviewOut(BaseModel):
    scope: ReclassificationScope
    total_candidates: int
    would_change: int
    breakdown: list[CategoryPreviewBreakdownOut]

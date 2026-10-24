from pydantic import BaseModel


class PositionChangeOut(BaseModel):
    asset: str
    account: str
    currency: str
    old_quantity: str | None
    new_quantity: str
    old_average_cost: str | None
    new_average_cost: str
    old_realized_pl: str | None
    new_realized_pl: str


class PositionsRecomputePreviewOut(BaseModel):
    """Anteprima sincrona (nessuna scrittura): cosa cambierebbe lanciando il
    ricalcolo vero."""

    checked: int
    changed: int
    changes: list[PositionChangeOut]


class PositionsRecomputeTriggered(BaseModel):
    job_id: str

"""Cruscotto "Attività" (vedi app/services/activity_service.py): vista di
sola lettura, nessuna scrittura qui — stesso principio di /jobs."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.schemas.activity import ActivityListOut
from app.services.activity_service import list_activity

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=ActivityListOut)
async def get_activity(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ActivityListOut:
    items = await list_activity(db, workspace_id)
    return ActivityListOut(items=items)

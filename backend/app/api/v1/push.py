"""Registrazione dei dispositivi per le notifiche push (app mobile)."""
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.push_device import PushDevice
from app.models.user import User
from app.services import push_service

router = APIRouter(prefix="/push", tags=["push"])


class PushStatusOut(BaseModel):
    # Il server ha le credenziali FCM? Se no l'app nasconde l'opzione.
    configured: bool
    devices: int


class PushDeviceIn(BaseModel):
    token: str = Field(min_length=10, max_length=4096)
    platform: str = Field(pattern="^(android|ios)$")


class PushDeviceDelete(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


@router.get("/status", response_model=PushStatusOut)
async def push_status(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PushStatusOut:
    count = await db.scalar(select(func.count()).select_from(PushDevice).where(PushDevice.owner_user_id == user.id))
    return PushStatusOut(configured=push_service.is_configured(), devices=int(count or 0))


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(
    payload: PushDeviceIn,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = insert(PushDevice).values(
        workspace_id=workspace_id, owner_user_id=user.id, platform=payload.platform, token=payload.token
    )
    # Stesso telefono che si ri-registra: si aggiorna solo `last_seen_at`.
    stmt = stmt.on_conflict_do_update(
        constraint="uq_push_devices_owner_token", set_={"last_seen_at": func.now(), "platform": payload.platform}
    )
    await db.execute(stmt)
    await db.commit()


@router.delete("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
    payload: PushDeviceDelete,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(delete(PushDevice).where(PushDevice.owner_user_id == user.id, PushDevice.token == payload.token))
    await db.commit()

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.bank import Bank
from app.schemas.banks import BankOut

router = APIRouter(prefix="/banks", tags=["banks"])


@router.get("", response_model=list[BankOut])
async def list_banks(
    _user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Bank]:
    result = await db.execute(select(Bank).order_by(Bank.name))
    return list(result.scalars().all())

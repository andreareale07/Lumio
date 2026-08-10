import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.models.financial_account import FinancialAccount
from app.schemas.accounts import FinancialAccountCreate, FinancialAccountOut, FinancialAccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _get_account_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> FinancialAccount:
    account = await db.get(FinancialAccount, account_id)
    # La RLS gia' impedisce di leggere righe di altri workspace (tornerebbero
    # None), ma il controllo esplicito sul workspace_id resta comunque il
    # primo livello di isolamento richiesto da SPEC §7 — non ci si affida
    # solo al database.
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


@router.post("", response_model=FinancialAccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: FinancialAccountCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> FinancialAccount:
    account = FinancialAccount(workspace_id=workspace_id, **payload.model_dump())
    db.add(account)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid bank reference") from exc
    return account


@router.get("", response_model=list[FinancialAccountOut])
async def list_accounts(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[FinancialAccount]:
    result = await db.execute(
        select(FinancialAccount)
        .where(FinancialAccount.workspace_id == workspace_id)
        .order_by(FinancialAccount.created_at)
    )
    return list(result.scalars().all())


@router.get("/{account_id}", response_model=FinancialAccountOut)
async def get_account(
    account_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> FinancialAccount:
    return await _get_account_or_404(db, workspace_id, account_id)


@router.patch("/{account_id}", response_model=FinancialAccountOut)
async def update_account(
    account_id: uuid.UUID,
    payload: FinancialAccountUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> FinancialAccount:
    account = await _get_account_or_404(db, workspace_id, account_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid bank reference") from exc
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    account = await _get_account_or_404(db, workspace_id, account_id)
    await db.delete(account)
    await db.commit()

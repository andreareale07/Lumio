import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.models.asset import Asset
from app.models.financial_account import FinancialAccount
from app.models.position import Position
from app.schemas.positions import PositionManualEdit, PositionOut
from app.services.position_service import apply_manual_position_edit

router = APIRouter(prefix="/positions", tags=["portfolio"])


@router.get("", response_model=list[PositionOut])
async def list_positions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    financial_account_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
) -> list[Position]:
    query = select(Position).where(Position.workspace_id == workspace_id)
    if financial_account_id is not None:
        query = query.where(Position.financial_account_id == financial_account_id)
    if asset_id is not None:
        query = query.where(Position.asset_id == asset_id)
    result = await db.execute(query.order_by(Position.created_at))
    return list(result.scalars().all())


@router.get("/{position_id}", response_model=PositionOut)
async def get_position(
    position_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Position:
    position = await db.get(Position, position_id)
    if position is None or position.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position not found")
    return position


@router.put("/by-account/{account_id}/asset/{asset_id}", response_model=PositionOut)
async def edit_position_manually(
    account_id: uuid.UUID,
    asset_id: uuid.UUID,
    payload: PositionManualEdit,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Position:
    """SPEC/decisione M09: modifica manuale della posizione, per l'onboarding
    di un portafoglio preesistente senza doverne ricostruire lo storico
    completo. Traduce l'input in un movimento `adjustment` (vedi
    `position_service.py`) — mai un UPDATE diretto su `positions`. Funziona
    anche se la posizione non esiste ancora (la crea dal nulla)."""
    account = await db.get(FinancialAccount, account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid financial_account_id")
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid asset_id")

    position = await apply_manual_position_edit(
        db,
        workspace_id,
        account_id,
        asset_id,
        asset.currency,
        payload.quantity,
        payload.average_cost,
        payload.notes,
    )
    # Si ritorna l'istanza gia' in sessione, MAI una query dopo il commit:
    # SET LOCAL app.current_user_id scade al commit (lumio-rls-gotchas), una
    # SELECT successiva girerebbe senza identita' RLS valida. Vedi docstring
    # di apply_manual_position_edit.
    await db.commit()
    return position

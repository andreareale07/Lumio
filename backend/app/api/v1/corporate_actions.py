import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.user import User
from app.schemas.corporate_actions import (
    CorporateActionSuggestionsOut,
    ExpireAssetRequest,
    ExpireAssetResult,
    ExpirySuggestionOut,
    MergeAssetsRequest,
    SplitSuggestionOut,
)
from app.services import corporate_action_service as service
from app.worker.queue import enqueue_snapshot_backfill

router = APIRouter(prefix="/corporate-actions", tags=["portfolio"])


@router.get("/suggestions", response_model=CorporateActionSuggestionsOut)
async def list_suggestions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> CorporateActionSuggestionsOut:
    splits = await service.list_split_suggestions(db, workspace_id)
    expirations = await service.list_expiry_suggestions(db, workspace_id, date.today())
    return CorporateActionSuggestionsOut(
        splits=[
            SplitSuggestionOut(
                source_asset_id=uuid.UUID(s.calc.source_asset_id),
                target_asset_id=uuid.UUID(s.calc.target_asset_id),
                source_label=s.source_label,
                target_label=s.target_label,
                source_quantity=s.source_quantity,
                target_quantity=s.target_quantity,
                ratio=s.calc.ratio,
                split_date=s.calc.split_date,
                confidence=s.calc.confidence,
                quantity_matched=s.calc.quantity_matched,
            )
            for s in splits
        ],
        expirations=[ExpirySuggestionOut(**vars(e)) for e in expirations],
    )


@router.post("/merge-assets", status_code=status.HTTP_204_NO_CONTENT)
async def merge_assets(
    payload: MergeAssetsRequest,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        affected_from = await service.merge_assets(
            db, workspace_id, payload.source_asset_id, payload.target_asset_id, payload.ratio, payload.split_date
        )
    except service.CorporateActionError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    # Il valore degli investimenti cambia da `affected_from` in poi: gli snapshot
    # del patrimonio gia' salvati (dashboard, grafico) vanno ricostruiti, altrimenti
    # restano quelli calcolati con la posizione sbagliata.
    await enqueue_snapshot_backfill(workspace_id, user.id, date_from=affected_from)


@router.post("/expire", response_model=ExpireAssetResult)
async def expire_asset(
    payload: ExpireAssetRequest,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ExpireAssetResult:
    try:
        closed = await service.expire_asset(db, workspace_id, payload.asset_id, payload.expiry_date)
    except service.CorporateActionError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    await enqueue_snapshot_backfill(workspace_id, user.id, date_from=payload.expiry_date)
    return ExpireAssetResult(closed_positions=closed)

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.user import User
from app.schemas.job_runs import JobRunOut
from app.schemas.maintenance import (
    PositionChangeOut,
    PositionsRecomputePreviewOut,
    PositionsRecomputeTriggered,
)
from app.services.job_run_tracker import get_latest_run
from app.services.position_service import recompute_all_positions
from app.worker.jobs.positions_recompute_job import JOB_KIND, change_to_dict
from app.worker.queue import enqueue_positions_recompute

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/positions-recompute/preview", response_model=PositionsRecomputePreviewOut)
async def preview_positions_recompute(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> PositionsRecomputePreviewOut:
    """Anteprima sincrona: esegue il ricalcolo e scarta tutto (rollback), cosi'
    l'utente vede cosa cambierebbe prima di lanciare il job vero."""
    report = await recompute_all_positions(db, workspace_id)
    await db.rollback()
    return PositionsRecomputePreviewOut(
        checked=report.checked,
        changed=len(report.changes),
        changes=[PositionChangeOut(**change_to_dict(c)) for c in report.changes],
    )


@router.post(
    "/positions-recompute", response_model=PositionsRecomputeTriggered, status_code=status.HTTP_202_ACCEPTED
)
async def trigger_positions_recompute(
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> PositionsRecomputeTriggered:
    """Innesca il job di ricalcolo — stesso principio anti-doppio-click di
    `trigger_reclassification`: se e' gia' 'running' ritorna lo stesso job_id."""
    current = await get_latest_run(db, workspace_id, JOB_KIND)
    if current is not None and current.status == "running":
        return PositionsRecomputeTriggered(job_id=current.job_id or "")
    job_id = await enqueue_positions_recompute(workspace_id, user.id)
    return PositionsRecomputeTriggered(job_id=job_id)


@router.get("/positions-recompute/status", response_model=JobRunOut | None)
async def get_positions_recompute_status(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> JobRunOut | None:
    run = await get_latest_run(db, workspace_id, JOB_KIND)
    return JobRunOut.model_validate(run) if run else None

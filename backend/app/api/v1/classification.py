import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.user import User
from app.schemas.classification import (
    CategoryPreviewBreakdownOut,
    ReclassificationPreviewOut,
    ReclassifyRequest,
    ReclassifyTriggered,
)
from app.schemas.job_runs import JobRunOut
from app.services import job_events
from app.services.audit_log_service import log_event
from app.services.classification_preview import preview_reclassification
from app.services.job_run_tracker import get_latest_run
from app.worker.jobs.reclassification_job import JOB_KIND, NAMESPACE
from app.worker.queue import enqueue_reclassification

router = APIRouter(prefix="/classification", tags=["classification"])


@router.get("/reclassify/preview", response_model=ReclassificationPreviewOut)
async def get_reclassification_preview(
    scope: str = "uncategorized",
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ReclassificationPreviewOut:
    """Anteprima sincrona (solo livelli deterministici, nessuna scrittura,
    nessuna chiamata AI): rende l'operazione non spaventosa prima di
    lanciare il job vero, che puo' scorrere migliaia di transazioni."""
    preview = await preview_reclassification(db, workspace_id, scope)
    return ReclassificationPreviewOut(
        scope=preview.scope,
        total_candidates=preview.total_candidates,
        would_change=preview.would_change,
        breakdown=[
            CategoryPreviewBreakdownOut(
                category_id=b.category_id,
                category_code=b.category_code,
                category_name=b.category_name,
                count=b.count,
                examples=b.examples,
            )
            for b in preview.breakdown
        ],
    )


@router.post("/reclassify", response_model=ReclassifyTriggered, status_code=status.HTTP_202_ACCEPTED)
async def trigger_reclassification(
    payload: ReclassifyRequest,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ReclassifyTriggered:
    """Innesca il job di riclassificazione — stesso principio anti-doppio-
    click (via `job_runs`) di `trigger_snapshot_rebuild`/
    `trigger_market_data_refresh`: se e' gia' 'running', ritorna lo stesso
    job_id invece di accodarne un secondo."""
    current = await get_latest_run(db, workspace_id, JOB_KIND)
    if current is not None and current.status == "running":
        return ReclassifyTriggered(job_id=current.job_id or "")

    job_id = await enqueue_reclassification(workspace_id, user.id, payload.scope, payload.run_ai)
    await log_event(
        db, workspace_id, user.id, "RECLASSIFICATION_RUN",
        entity_type="workspace", entity_id=workspace_id,
        metadata={"scope": payload.scope, "run_ai": payload.run_ai},
    )
    await db.commit()
    return ReclassifyTriggered(job_id=job_id)


@router.get("/reclassify/status", response_model=JobRunOut | None)
async def get_reclassification_status(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> JobRunOut | None:
    run = await get_latest_run(db, workspace_id, JOB_KIND)
    return JobRunOut.model_validate(run) if run else None


@router.get("/reclassify/events")
async def stream_reclassification_events(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> StreamingResponse:
    """Mirror di `/imports/{id}/events`, ma con `topic_id=workspace_id` (un
    solo job di riclassificazione alla volta per workspace, non per import)
    e namespace 'reclassification'."""
    return StreamingResponse(
        job_events.stream(workspace_id, namespace=NAMESPACE),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

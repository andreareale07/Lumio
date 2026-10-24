import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.ai_run_event import AIRunEvent
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.ai_engine import (
    AIEngineImportOut,
    AIEngineProfileOut,
    AIEngineStatusOut,
    AIRetryResultOut,
    AIRunEventListOut,
    AIRunEventOut,
)
from app.services.ai_classification_trigger import prepare_ai_classification_trigger
from app.services.ai_profile_service import get_active_profile
from app.services.ai_run_event_service import list_events
from app.services.system_classification import AI_EXCLUDED_TRANSACTION_TYPES
from app.worker.queue import enqueue_classify_import_job

router = APIRouter(prefix="/ai-engine", tags=["ai-engine"])

_RECENT_IMPORTS_LIMIT = 20
_RETRYABLE_AI_STATUSES = (None, "failed", "skipped", "completed")


def _eligible_filter():
    return (
        Transaction.category_id.is_(None),
        Transaction.transaction_type.notin_(AI_EXCLUDED_TRANSACTION_TYPES),
    )


@router.get("/status", response_model=AIEngineStatusOut)
async def get_ai_engine_status(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AIEngineStatusOut:
    profile = await get_active_profile(db, workspace_id)

    uncategorized = (
        await db.execute(
            select(func.count()).select_from(Transaction).where(Transaction.workspace_id == workspace_id, *_eligible_filter())
        )
    ).scalar_one()

    since = datetime.now(UTC) - timedelta(hours=24)
    errors_24h, last_error_at = (
        await db.execute(
            select(func.count(), func.max(AIRunEvent.created_at)).where(
                AIRunEvent.workspace_id == workspace_id,
                AIRunEvent.severity == "error",
                AIRunEvent.created_at >= since,
            )
        )
    ).one()

    imports = list(
        (
            await db.execute(
                select(Import)
                .where(Import.workspace_id == workspace_id, Import.status == "completed")
                .order_by(Import.completed_at.desc().nulls_last(), Import.created_at.desc())
                .limit(_RECENT_IMPORTS_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    per_import = {}
    if imports:
        rows = (
            await db.execute(
                select(Transaction.import_id, func.count())
                .where(
                    Transaction.workspace_id == workspace_id,
                    Transaction.import_id.in_([i.id for i in imports]),
                    *_eligible_filter(),
                )
                .group_by(Transaction.import_id)
            )
        ).all()
        per_import = {import_id: count for import_id, count in rows}

    return AIEngineStatusOut(
        active_profile=(
            AIEngineProfileOut(name=profile.name, provider=profile.provider, model=profile.model)
            if profile is not None
            else None
        ),
        uncategorized_eligible=uncategorized,
        errors_last_24h=errors_24h,
        last_error_at=last_error_at,
        recent_imports=[
            AIEngineImportOut(
                import_id=i.id,
                filename=i.filename,
                completed_at=i.completed_at,
                ai_status=i.ai_classification_status,
                ai_total=i.ai_transactions_total,
                ai_classified=i.ai_transactions_classified,
                ai_error_message=i.ai_classification_error_message,
                uncategorized_eligible=per_import.get(i.id, 0),
                can_retry=(
                    profile is not None
                    and i.ai_classification_status in _RETRYABLE_AI_STATUSES
                    and per_import.get(i.id, 0) > 0
                ),
            )
            for i in imports
        ],
    )


@router.get("/events", response_model=AIRunEventListOut)
async def list_ai_engine_events(
    severity: str | None = Query(default=None, pattern="^(error|warning|info)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AIRunEventListOut:
    events, total = await list_events(db, workspace_id, severity, limit, offset)
    import_ids = {e.import_id for e in events if e.import_id is not None}
    filenames: dict[uuid.UUID, str] = {}
    if import_ids:
        rows = (
            await db.execute(select(Import.id, Import.filename).where(Import.id.in_(import_ids)))
        ).all()
        filenames = {import_id: filename for import_id, filename in rows}
    return AIRunEventListOut(
        items=[
            AIRunEventOut(
                id=e.id,
                run_kind=e.run_kind,
                import_id=e.import_id,
                import_filename=filenames.get(e.import_id) if e.import_id else None,
                severity=e.severity,
                code=e.code,
                message=e.message,
                created_at=e.created_at,
            )
            for e in events
        ],
        total=total,
    )


@router.post("/imports/{import_id}/retry", response_model=AIRetryResultOut, status_code=status.HTTP_202_ACCEPTED)
async def retry_import_ai_classification(
    import_id: uuid.UUID,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AIRetryResultOut:
    """Rilancia la classificazione AI su un import GIA' completato: classifica
    solo le righe ancora senza categoria (mai quelle corrette a mano, mai le
    gia' classificate), quindi e' sicuro ripeterla."""
    import_row = await db.get(Import, import_id)
    if import_row is None or import_row.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    if import_row.status != "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "L'import non è ancora completato")
    if import_row.ai_classification_status in ("pending", "running"):
        raise HTTPException(status.HTTP_409_CONFLICT, "La classificazione AI di questo import è già in corso")
    if await get_active_profile(db, workspace_id) is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Nessun profilo AI attivo: attivane uno in Impostazioni > AI"
        )

    import_row.ai_transactions_classified = 0
    import_row.ai_classification_error_message = None
    should_enqueue = await prepare_ai_classification_trigger(db, workspace_id, import_row)
    result = AIRetryResultOut(
        ai_status=import_row.ai_classification_status, ai_total=import_row.ai_transactions_total
    )
    await db.commit()
    if should_enqueue:
        await enqueue_classify_import_job(import_row.id, import_row.created_by_user_id, rerun=True)
    return result

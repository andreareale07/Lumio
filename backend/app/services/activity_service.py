"""Aggrega in un'unica lista tutte le elaborazioni del workspace per il
cruscotto "Attività": import non terminali (+ la loro classificazione AI,
disaccoppiata), l'ultima riclassificazione, e l'ultima esecuzione di ogni
job schedulato (refresh prezzi, snapshot, export Google Sheets) — questi
ultimi mostrati SEMPRE, non solo quando in corso, cosi' l'utente vede anche
"cosa ha fatto l'ultima volta il sistema" (scelta confermata con l'utente:
niente filtro sui job veloci/schedulati).
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.import_ import Import
from app.models.job_run import JOB_KINDS
from app.schemas.activity import ActivityItemOut
from app.services.job_registry import JOB_DESCRIPTORS
from app.services.job_run_tracker import get_latest_run

_ACTIVE_IMPORT_STATUSES = ("uploaded", "queued", "processing", "parsing", "classifying", "ready_for_review")
_ACTIVE_AI_CLASSIFICATION_STATUSES = ("pending", "running")
# Un fallimento resta visibile nel cruscotto per un po', non solo mentre e'
# "in corso": un job che fallisce è esattamente il caso che l'utente ha
# più bisogno di vedere, non deve sparire dalla lista appena il worker
# smette di lavorarci (bug reale, scoperto perché un fallimento AI durante
# un import reale non compariva affatto in questa vista). Non per sempre,
# altrimenti la lista si riempirebbe di fallimenti vecchi mai puliti.
_RECENT_FAILURE_WINDOW = timedelta(hours=6)

_JOB_RUN_LABEL_KEYS = {d.kind: d.name_key for d in JOB_DESCRIPTORS}
_JOB_RUN_EVENTS_URL = {
    "reclassification": "/classification/reclassify/events",
    "google_sheets_export": "/integrations/google/export-events",
    # FETTA 3 (storico patrimonio ricostruito): stessa ragione di
    # "reclassification" — un job triggerabile che puo' durare minuti/ore,
    # progresso live nel cruscotto Attivita' senza codice frontend nuovo.
    "snapshot_backfill": "/portfolios/snapshots/backfill/events",
}


def _import_status_activity_status(status: str) -> str:
    return "failed" if status == "failed" else "running"


async def _import_items(db: AsyncSession, workspace_id: uuid.UUID) -> list[ActivityItemOut]:
    cutoff = datetime.now(UTC) - _RECENT_FAILURE_WINDOW
    result = await db.execute(
        select(Import).where(
            Import.workspace_id == workspace_id,
            or_(
                Import.status.in_(_ACTIVE_IMPORT_STATUSES),
                Import.ai_classification_status.in_(_ACTIVE_AI_CLASSIFICATION_STATUSES),
                (Import.status == "failed") & (Import.updated_at >= cutoff),
                (Import.ai_classification_status == "failed") & (Import.updated_at >= cutoff),
            ),
        )
    )
    items: list[ActivityItemOut] = []
    for import_row in result.scalars().all():
        import_is_active = import_row.status in _ACTIVE_IMPORT_STATUSES
        import_recently_failed = import_row.status == "failed" and import_row.updated_at >= cutoff
        if import_is_active or import_recently_failed:
            items.append(
                ActivityItemOut(
                    kind="import",
                    label=f"Import {import_row.filename}",
                    status=_import_status_activity_status(import_row.status),
                    events_url=f"/imports/{import_row.id}/events",
                    started_at=import_row.created_at,
                    finished_at=import_row.completed_at or (import_row.updated_at if import_recently_failed else None),
                    message=import_row.error_message,
                    processed=import_row.transactions_imported,
                    total=import_row.transactions_found or None,
                )
            )

        ai_is_active = import_row.ai_classification_status in _ACTIVE_AI_CLASSIFICATION_STATUSES
        ai_recently_failed = import_row.ai_classification_status == "failed" and import_row.updated_at >= cutoff
        if ai_is_active or ai_recently_failed:
            items.append(
                ActivityItemOut(
                    kind="ai_classification",
                    label=f"Classificazione AI — {import_row.filename}",
                    status=import_row.ai_classification_status,
                    events_url=f"/imports/{import_row.id}/ai-classification-events",
                    started_at=import_row.created_at,
                    finished_at=import_row.updated_at if ai_recently_failed else None,
                    message=import_row.ai_classification_error_message,
                    processed=import_row.ai_transactions_classified,
                    total=import_row.ai_transactions_total or None,
                )
            )
    return items


async def _job_run_items(db: AsyncSession, workspace_id: uuid.UUID) -> list[ActivityItemOut]:
    items: list[ActivityItemOut] = []
    for job_kind in JOB_KINDS:
        if job_kind == "google_sheets_export" and not get_settings().google_enabled:
            continue
        run = await get_latest_run(db, workspace_id, job_kind)
        if run is None:
            continue
        items.append(
            ActivityItemOut(
                kind=job_kind,
                label=job_kind,
                label_key=_JOB_RUN_LABEL_KEYS.get(job_kind),
                status=run.status,
                events_url=_JOB_RUN_EVENTS_URL.get(job_kind),
                started_at=run.started_at,
                finished_at=run.finished_at,
                message=run.message,
            )
        )
    return items


async def list_activity(db: AsyncSession, workspace_id: uuid.UUID) -> list[ActivityItemOut]:
    items = await _import_items(db, workspace_id)
    items.extend(await _job_run_items(db, workspace_id))

    # In corso prima, poi per data di inizio decrescente: l'utente guarda
    # prima cosa sta succedendo ORA, il resto e' storico recente.
    def _sort_key(item: ActivityItemOut) -> tuple:
        is_active = item.status in ("running", "pending")
        timestamp = item.started_at.timestamp() if item.started_at else float("-inf")
        return (0 if is_active else 1, -timestamp)

    items.sort(key=_sort_key)
    return items

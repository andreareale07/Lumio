"""Job schedulato (cron giornaliero) + trigger manuale per lo snapshot di
patrimonio/portfolio (SPEC §31, §37 — DoD M09: "storico patrimonio
consultabile via snapshot, non ricalcolato da zero ogni volta"). Per ogni
workspace scrive (upsert) lo snapshot del giorno corrente — la logica di
calcolo vive in `app/services/portfolio_analytics.py`, condivisa col
possibile ricalcolo puntuale via API.
"""
import logging
import uuid

from app.db.rls import rls_session
from app.services.job_run_tracker import tracked_job_run
from app.services.portfolio_analytics import SnapshotRunSummary, write_daily_snapshots
from app.services.system_settings_service import is_job_enabled
from app.worker.jobs.market_data import list_workspace_owners

logger = logging.getLogger(__name__)

JOB_KIND = "snapshot_rebuild"


def _snapshot_message(summary: SnapshotRunSummary) -> str:
    return f"Snapshot ricalcolato per il {summary.snapshot_date.isoformat()} ({summary.portfolios} portfolio)."


async def snapshot_job(ctx) -> None:
    # Stesso principio di refresh_market_data_job: riguarda solo l'esecuzione
    # automatica schedulata, il trigger manuale resta sempre disponibile.
    if not await is_job_enabled(JOB_KIND):
        logger.info("snapshot: cron disattivato da configurazione, nessuna esecuzione automatica")
        return
    for workspace_id, owner_user_id in await list_workspace_owners():
        try:
            async with tracked_job_run(workspace_id, owner_user_id, JOB_KIND) as run:
                async with rls_session(owner_user_id) as db:
                    summary = await write_daily_snapshots(db, workspace_id)
                    await db.commit()
                run.message = _snapshot_message(summary)
        except Exception:
            # Stesso principio di app/worker/jobs/market_data.py: un
            # workspace fallito non deve bloccare gli altri.
            logger.exception("snapshot cron falito per workspace %s", workspace_id)


async def write_snapshot_for_workspace(ctx, workspace_id: str, user_id: str) -> None:
    """Job arq per il trigger manuale (`POST /portfolio/snapshots/rebuild`,
    vedi `app/worker/queue.py`) — UN solo workspace, stessa logica del cron
    ma senza attendere tutti gli altri. `user_id` e' chi ha premuto il
    pulsante (gia' verificato membro del workspace), non serve l'owner."""
    ws_id, uid = uuid.UUID(workspace_id), uuid.UUID(user_id)
    async with tracked_job_run(ws_id, uid, JOB_KIND) as run:
        async with rls_session(uid) as db:
            summary = await write_daily_snapshots(db, ws_id)
            await db.commit()
        run.message = _snapshot_message(summary)

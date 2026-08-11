"""Job schedulato (cron giornaliero) + trigger manuale per lo snapshot di
patrimonio/portfolio (SPEC §31, §37 — DoD M09: "storico patrimonio
consultabile via snapshot, non ricalcolato da zero ogni volta"). Per ogni
workspace scrive (upsert) lo snapshot del giorno corrente — la logica di
calcolo vive in `app/services/portfolio_analytics.py`, condivisa col
possibile ricalcolo puntuale via API.
"""
import uuid

from app.db.rls import rls_session
from app.services.portfolio_analytics import write_daily_snapshots
from app.worker.jobs.market_data import list_workspace_owners


async def snapshot_job(ctx) -> None:
    for workspace_id, owner_user_id in await list_workspace_owners():
        async with rls_session(owner_user_id) as db:
            await write_daily_snapshots(db, workspace_id)
            await db.commit()


async def write_snapshot_for_workspace(ctx, workspace_id: str, user_id: str) -> None:
    """Job arq per il trigger manuale (`POST /portfolio/snapshots/rebuild`,
    vedi `app/worker/queue.py`) — UN solo workspace, stessa logica del cron
    ma senza attendere tutti gli altri. `user_id` e' chi ha premuto il
    pulsante (gia' verificato membro del workspace), non serve l'owner."""
    async with rls_session(uuid.UUID(user_id)) as db:
        await write_daily_snapshots(db, uuid.UUID(workspace_id))
        await db.commit()

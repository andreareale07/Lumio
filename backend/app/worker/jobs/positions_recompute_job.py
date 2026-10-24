"""Job di ricalcolo delle posizioni dai movimenti (Impostazioni > Manutenzione).

`positions` e' un valore salvato: dopo una correzione al calcolo (o una
modifica fatta fuori dai percorsi normali) i valori gia' salvati restano
stantii finche' un loro movimento non cambia. Questo job li ricalcola tutti
con l'identita' RLS dell'utente che lo ha lanciato.

Il resoconto di cosa e' cambiato (titolo, conto, utile realizzato/quantita'/
costo medio prima e dopo) viene salvato in `job_runs.details`, cosi' resta
consultabile in UI invece di sparire nel log del worker.
"""
import logging
import uuid
from decimal import Decimal

from app.db.rls import rls_session
from app.services.job_run_tracker import get_latest_run, tracked_job_run
from app.services.position_service import PositionChange, RecomputeReport, recompute_all_positions

logger = logging.getLogger("lumio.worker.positions_recompute_job")

JOB_KIND = "positions_recompute"
# Oltre questa soglia l'elenco nel resoconto viene troncato (il conteggio resta
# esatto): una riga JSONB non deve crescere senza limite.
MAX_DETAIL_ROWS = 500


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def change_to_dict(change: PositionChange) -> dict:
    return {
        "asset": change.asset_name,
        "account": change.account_name,
        "currency": change.currency,
        "old_quantity": _text(change.old_quantity),
        "new_quantity": _text(change.new_quantity),
        "old_average_cost": _text(change.old_average_cost),
        "new_average_cost": _text(change.new_average_cost),
        "old_realized_pl": _text(change.old_realized_pl),
        "new_realized_pl": _text(change.new_realized_pl),
    }


def report_to_details(report: RecomputeReport) -> dict:
    return {
        "checked": report.checked,
        "changed": len(report.changes),
        "truncated": len(report.changes) > MAX_DETAIL_ROWS,
        "changes": [change_to_dict(c) for c in report.changes[:MAX_DETAIL_ROWS]],
    }


_REPORT_KEYS = ("checked", "changed", "truncated", "changes")


async def _last_report_with_changes(ws_id: uuid.UUID, uid: uuid.UUID) -> dict | None:
    """Resoconto dell'ultima esecuzione che ha DAVVERO modificato qualcosa: una
    riesecuzione a vuoto sovrascriverebbe `details` con "0 modifiche" e
    farebbe sparire l'unica traccia utile di cosa era cambiato. Va letto PRIMA
    di `tracked_job_run`, che azzera `details` all'avvio."""
    async with rls_session(uid) as db:
        previous = await get_latest_run(db, ws_id, JOB_KIND)
    if previous is None or not previous.details:
        return None
    if previous.details.get("changed"):
        at = previous.finished_at or previous.started_at
        return {"at": at.isoformat(), **{key: previous.details.get(key) for key in _REPORT_KEYS}}
    return previous.details.get("previous_changes")


async def positions_recompute_job(ctx, workspace_id: str, user_id: str) -> None:
    ws_id = uuid.UUID(workspace_id)
    uid = uuid.UUID(user_id)
    carried = await _last_report_with_changes(ws_id, uid)

    async with tracked_job_run(ws_id, uid, JOB_KIND) as run:
        async with rls_session(uid) as db:
            report = await recompute_all_positions(db, ws_id)
            await db.commit()
        run.message = f"{len(report.changes)} posizioni aggiornate su {report.checked} controllate."
        run.details = report_to_details(report)
        if not report.changes and carried is not None:
            run.details["previous_changes"] = carried
        logger.info("positions recompute workspace=%s %s", ws_id, run.message)

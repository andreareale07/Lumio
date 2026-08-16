"""Rilevatore GENERICO di job bloccati (worker morto a meta' esecuzione,
kill -9, OOM, ecc.) — nessun job in questa app ha oggi un meccanismo di
lease/heartbeat, limite documentato e accettato in piu' punti (vedi
`app/worker/jobs/import_job.py`, `app/worker/jobs/ai_classification_job.py`):
se il worker muore mentre un job e' in uno stato non-terminale, quella riga
resta bloccata per sempre, senza alcuna transizione automatica.

Questo modulo NON e' specifico per un tipo di job: e' un registro di check
(`_CHECKS`), ognuno dei quali sa solo "come trovare le mie righe non-
terminali piu' vecchie della soglia" e "come marcarle fallite" — il motore
che li esegue (`expire_stale_jobs`, chiamato dal cron in
`app/worker/jobs/job_health_job.py`) non conosce alcun dettaglio di
Import/JobRun. Aggiungere un futuro tipo di job al rilevamento significa
solo aggiungere un `_StaleJobCheck` qui, non toccare il motore.

Le soglie ("quanto tempo senza attivita' prima di considerarlo morto") non
sono cablate nel codice: vivono in `system_settings` (tabella di istanza,
vedi `app/models/system_setting.py`) e vengono lette ad ogni esecuzione del
cron, non una volta sola all'avvio del processo — un cambio di soglia ha
effetto dal giro successivo, senza riavviare il worker.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.job_run import JOB_KINDS, JobRun
from app.services import job_events
from app.services.system_settings_service import get_setting_value
from app.worker.jobs.market_data import list_workspace_owners

logger = logging.getLogger("lumio.worker.job_health")

_STALE_JOB_MESSAGE = (
    "Job interrotto: nessuna attivita' rilevata da troppo tempo (il processo "
    "che lo eseguiva e' probabilmente terminato in modo anomalo)."
)


@dataclass
class _StaleJobCheck:
    name: str
    threshold_setting_key: str
    # Riceve la sessione RLS gia' aperta per il workspace corrente e la
    # soglia in secondi; ritorna quante righe ha marcato fallite.
    run: Callable[[AsyncSession, uuid.UUID, int], Awaitable[int]]


async def _get_threshold_seconds(key: str) -> int:
    # Default 0 (non un numero a caso): expire_stale_jobs salta il check
    # quando la soglia e' <= 0, quindi una chiave mancante disattiva
    # silenziosamente solo QUEL check, invece di rilevare con un valore
    # inventato.
    return int(await get_setting_value(key, 0))


async def _expire_stale_imports(db: AsyncSession, workspace_id: uuid.UUID, threshold_seconds: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_seconds)
    result = await db.execute(
        select(Import).where(
            Import.workspace_id == workspace_id,
            Import.status.in_(("processing", "parsing")),
            Import.updated_at < cutoff,
        )
    )
    stale_rows = list(result.scalars().all())
    for import_row in stale_rows:
        import_row.status = "failed"
        import_row.error_message = "Impossibile completare l'import: nessuna attivita' rilevata da troppo tempo"
        await job_events.emit(import_row.id, "job.failed", message="Import interrotto")
    return len(stale_rows)


async def _expire_stale_ai_classifications(
    db: AsyncSession, workspace_id: uuid.UUID, threshold_seconds: int
) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_seconds)
    result = await db.execute(
        select(Import).where(
            Import.workspace_id == workspace_id,
            Import.ai_classification_status.in_(("pending", "running")),
            Import.updated_at < cutoff,
        )
    )
    stale_rows = list(result.scalars().all())
    for import_row in stale_rows:
        import_row.ai_classification_status = "failed"
        await job_events.emit(
            import_row.id, "job.failed", namespace="ai_classification", message="Classificazione AI interrotta"
        )
    return len(stale_rows)


def _make_job_run_check(job_kind: str) -> Callable[[AsyncSession, uuid.UUID, int], Awaitable[int]]:
    """Un check per singolo `job_kind` di `job_runs` (non uno condiviso su
    tutta la tabella): ogni tipo di job schedulato (refresh prezzi, snapshot,
    export Google Sheets) ha una propria soglia in system_settings, cosi' la
    UI puo' mostrarla/modificarla per job invece che come un unico valore
    che li riguarda tutti indistintamente."""

    async def _run(db: AsyncSession, workspace_id: uuid.UUID, threshold_seconds: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=threshold_seconds)
        result = await db.execute(
            select(JobRun).where(
                JobRun.workspace_id == workspace_id,
                JobRun.job_kind == job_kind,
                JobRun.status == "running",
                JobRun.started_at < cutoff,
            )
        )
        stale_rows = list(result.scalars().all())
        for job_run in stale_rows:
            job_run.status = "failed"
            job_run.finished_at = datetime.now(UTC)
            job_run.message = _STALE_JOB_MESSAGE[:500]
        return len(stale_rows)

    return _run


_CHECKS: list[_StaleJobCheck] = [
    _StaleJobCheck("import", "job_health.import.stale_after_seconds", _expire_stale_imports),
    _StaleJobCheck(
        "ai_classification", "job_health.ai_classification.stale_after_seconds", _expire_stale_ai_classifications
    ),
    *(
        _StaleJobCheck(job_kind, f"job_health.{job_kind}.stale_after_seconds", _make_job_run_check(job_kind))
        for job_kind in JOB_KINDS
    ),
]


async def expire_stale_jobs() -> dict[str, int]:
    """Esegue tutti i check registrati per ogni workspace esistente. Ritorna
    quante righe sono state marcate fallite per ciascun check (diagnostica
    per il log del cron, non esposto altrove)."""
    thresholds = {check.name: await _get_threshold_seconds(check.threshold_setting_key) for check in _CHECKS}
    totals = {check.name: 0 for check in _CHECKS}

    for workspace_id, owner_user_id in await list_workspace_owners():
        for check in _CHECKS:
            threshold = thresholds[check.name]
            if threshold <= 0:
                continue
            try:
                async with rls_session(owner_user_id) as db:
                    expired = await check.run(db, workspace_id, threshold)
                    if expired:
                        await db.commit()
                totals[check.name] += expired
            except Exception:
                # Stesso principio degli altri job cross-workspace (market_data/
                # snapshot): un workspace che fallisce il check non deve
                # bloccare gli altri o gli altri tipi di check.
                logger.exception(
                    "job_health: check '%s' fallito per workspace %s", check.name, workspace_id
                )

    return totals

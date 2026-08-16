"""Cron generico che rileva ed espira i job bloccati (worker morto a meta'
esecuzione) — vedi `app/services/job_health.py` per il motore e il registro
dei check, questo file e' solo il wrapper arq che lo schedula.
"""
import logging

from app.services.job_health import expire_stale_jobs
from app.services.system_settings_service import is_job_enabled

logger = logging.getLogger("lumio.worker.job_health_job")

JOB_KIND = "stale_job_reaper"


async def expire_stale_jobs_job(ctx) -> None:
    if not await is_job_enabled(JOB_KIND):
        # Il cron continua a scattare ogni 2 minuti (arq lo registra
        # all'avvio del processo, non si puo' rimuovere a runtime) — qui si
        # ferma subito senza fare nulla. Disattivarlo vuol dire, in pratica,
        # che nessun job bloccato da un crash del worker verra' piu'
        # rilevato automaticamente.
        logger.info("job_health: rilevatore disattivato da configurazione, nessun controllo eseguito")
        return

    totals = await expire_stale_jobs()
    expired = {name: count for name, count in totals.items() if count}
    if expired:
        logger.warning("job_health: job marcati falliti per stallo: %s", expired)

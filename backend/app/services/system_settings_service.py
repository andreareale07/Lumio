"""Lettura generica di `system_settings` (configurazione di istanza, vedi
`app/models/system_setting.py`) — un solo punto da cui sia il rilevatore di
job bloccati (`app/services/job_health.py`) sia le guardie enabled/disabled
nei job cron stessi leggono i propri valori, sempre dal DB e mai da una
cache di processo: un cambiamento ha effetto dal giro successivo del job
che lo consulta, senza richiedere un riavvio del worker.
"""
import logging

from app.db.base import async_session_factory
from app.models.system_setting import SystemSetting

logger = logging.getLogger("lumio.system_settings")


async def get_setting_value(key: str, default):
    async with async_session_factory() as session:
        setting = await session.get(SystemSetting, key)
    if setting is None:
        # Nessuna riga seed per questa chiave (es. migrazione non ancora
        # applicata in un ambiente vecchio): il default del CHIAMANTE, non
        # un valore inventato qui — ogni chiamante sa qual e' il
        # comportamento piu' sicuro in sua assenza.
        logger.warning("system_settings: chiave mancante %s, uso il default %r", key, default)
        return default
    return setting.value


async def is_job_enabled(job_kind: str) -> bool:
    """True se manca la riga (fail-open: un job storico senza questa
    configurazione resta attivo com'era prima che esistesse il toggle)."""
    return bool(await get_setting_value(f"jobs.{job_kind}.enabled", True))

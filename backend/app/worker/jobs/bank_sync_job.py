"""Job arq per la sincronizzazione Open Banking.

- `bank_sync_job`: trigger manuale ("Sincronizza ora"), un'unica connessione,
  con il contesto dell'utente presente (ignora intervallo e backoff).
- `bank_sync_all_job`: cron orario; ogni connessione attiva si sincronizza solo
  se e' trascorso l'intervallo configurato (`OPEN_BANKING_SYNC_INTERVAL_HOURS`,
  minimo 6 ore) e non e' in backoff dopo un errore. Un errore su una
  connessione non blocca le altre.
"""
import logging
import uuid

from sqlalchemy import text

from app.core.config import get_settings
from app.db.base import async_session_factory
from app.openbanking.base import PsuContext
from app.services import bank_sync_service

logger = logging.getLogger("lumio.worker.bank_sync")


async def bank_sync_job(
    ctx, connection_id: str, user_id: str, psu_ip: str | None = None, psu_user_agent: str | None = None
) -> None:
    summary = await bank_sync_service.sync_connection(
        uuid.UUID(connection_id),
        uuid.UUID(user_id),
        psu=PsuContext(ip_address=psu_ip, user_agent=psu_user_agent),
    )
    logger.info(
        "sync manuale %s: conti=%d nuovi=%d duplicati=%d errore=%s",
        connection_id,
        summary.accounts_synced,
        summary.imported,
        summary.duplicates,
        summary.error_code,
    )


async def _list_active_connections() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Enumerazione via la funzione SECURITY DEFINER `list_active_bank_connections()`
    (migration 0044): il cron non ha un'identita' RLS e le tabelle sono owner-only."""
    async with async_session_factory() as session:
        rows = (await session.execute(text("SELECT * FROM list_active_bank_connections()"))).all()
    return [(row.connection_id, row.owner_user_id) for row in rows]


async def bank_sync_all_job(ctx) -> None:
    if not get_settings().open_banking_enabled:
        return
    for connection_id, owner_user_id in await _list_active_connections():
        try:
            summary = await bank_sync_service.sync_connection(connection_id, owner_user_id, scheduled=True)
            if not summary.skipped:
                logger.info(
                    "sync pianificata %s: nuovi=%d errore=%s", connection_id, summary.imported, summary.error_code
                )
        except Exception:
            logger.exception("sync pianificata fallita per la connessione %s", connection_id)

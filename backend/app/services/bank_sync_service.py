"""Sincronizzazione dei movimenti da una connessione Open Banking.

Idempotente: ogni sync rilegge i movimenti dalla data dell'ultimo importato
meno una finestra di riconciliazione, scarta quelli gia' presenti per
`external_id` (identificativo della banca) e passa i restanti dalla pipeline
unica di import (dedup a fingerprint con REVIEW per i casi ambigui,
classificazione, riconoscimento trasferimenti): un `Import` con
`file_type='open_banking'` per ogni conto con movimenti nuovi.

Identita' RLS: il job gira con l'utente proprietario della connessione, mai con
BYPASSRLS. Nessuna query RLS dopo un commit nella stessa sessione: ogni blocco
apre la propria `rls_session` e fa un solo commit.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.redis import redis_client
from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.open_banking import BankConnection, BankConnectionAccount
from app.models.transaction import Transaction
from app.models.user import User
from app.openbanking.base import NormalizedTransaction, PsuContext
from app.openbanking.errors import (
    AuthorizationExpiredError,
    OpenBankingAuthError,
    OpenBankingError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.parsers.base import TransferCounterparty
from app.services import open_banking_service, push_service
from app.services.csv_import import ParsedRow
from app.services.transfer_recognition import is_internal_transfer

logger = logging.getLogger("lumio.bank_sync")

LOCK_TTL_SECONDS = 900
MANUAL_SYNC_COOLDOWN_SECONDS = 30
# Il limite di molte banche e' 4 letture al giorno senza utente presente.
MIN_INTERVAL_HOURS = 6
_ATTEMPT_TTL_AFTER_TRANSIENT_FAILURE = 3600
_ATTEMPT_TTL_AFTER_RATE_LIMIT = 12 * 3600
_EXTERNAL_ID_CHUNK = 500


def _lock_key(connection_id: uuid.UUID) -> str:
    return f"bank_sync:lock:{connection_id}"


def _attempt_key(connection_id: uuid.UUID) -> str:
    return f"bank_sync:attempt:{connection_id}"


def effective_interval_seconds() -> int:
    hours = max(MIN_INTERVAL_HOURS, get_settings().open_banking_sync_interval_hours)
    return hours * 3600


async def is_sync_running(connection_id: uuid.UUID) -> bool:
    return bool(await redis_client.exists(_lock_key(connection_id)))


async def try_acquire_lock(connection_id: uuid.UUID, ttl: int = LOCK_TTL_SECONDS) -> bool:
    """Lock esclusivo sulla connessione (lo stesso della sync): chi lo ottiene
    e' l'unico a leggere dalla banca o a cancellare i dati importati."""
    return bool(await redis_client.set(_lock_key(connection_id), "1", nx=True, ex=ttl))


async def release_lock(connection_id: uuid.UUID) -> None:
    await redis_client.delete(_lock_key(connection_id))


async def try_start_manual_sync(connection_id: uuid.UUID) -> bool:
    """Pausa minima tra due sincronizzazioni manuali: ogni lettura pesa sui
    limiti della banca. `False` se e' troppo presto."""
    return bool(
        await redis_client.set(f"bank_sync:manual:{connection_id}", "1", nx=True, ex=MANUAL_SYNC_COOLDOWN_SECONDS)
    )


@dataclass
class SyncSummary:
    accounts_synced: int = 0
    imported: int = 0
    duplicates: int = 0
    review_pending: int = 0
    error_code: str | None = None
    skipped: bool = False
    details: list[str] = field(default_factory=list)


def to_parsed_row(tx: NormalizedTransaction) -> ParsedRow:
    description = " ".join(tx.description.split()) or "Movimento"
    is_debit = tx.amount < 0
    return ParsedRow(
        transaction_date=tx.booking_date or tx.transaction_date,
        value_date=tx.value_date,
        description_raw=tx.description,
        description_normalized=description,
        amount=tx.amount,
        currency=tx.currency,
        direction="debit" if is_debit else "credit",
        # Solo il segno: la mappatura piu' specifica spetta alle regole/AI e
        # alle correzioni dell'utente (regola del progetto sui tipi).
        transaction_type="expense" if is_debit else "income",
        source_type_raw=tx.bank_transaction_code,
        reference=tx.reference,
        balance_after=tx.balance_after,
        counterparty_name=tx.counterparty_name,
        counterparty_iban=tx.counterparty_iban,
        external_id=tx.external_id,
    )


async def _existing_external_ids(db, workspace_id, financial_account_id, external_ids: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(external_ids), _EXTERNAL_ID_CHUNK):
        chunk = external_ids[start : start + _EXTERNAL_ID_CHUNK]
        rows = await db.scalars(
            select(Transaction.external_id).where(
                Transaction.workspace_id == workspace_id,
                Transaction.financial_account_id == financial_account_id,
                Transaction.external_id.in_(chunk),
            )
        )
        found.update(rows.all())
    return found


@dataclass
class _AccountJob:
    account_id: uuid.UUID
    provider_uid: str
    financial_account_id: uuid.UUID
    last_booked_date: date | None
    iban: str | None


async def sync_connection(
    connection_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    psu: PsuContext | None = None,
    scheduled: bool = False,
) -> SyncSummary:
    """Sincronizza tutti i conti attivi della connessione. `scheduled=True`
    (cron) rispetta l'intervallo minimo e il backoff dopo un errore; la sync
    manuale (utente presente, con `psu`) li ignora ma non il lock."""
    summary = SyncSummary()
    interval = effective_interval_seconds()

    if scheduled and not await redis_client.set(_attempt_key(connection_id), "1", nx=True, ex=interval):
        summary.skipped = True
        return summary
    if not await redis_client.set(_lock_key(connection_id), "1", nx=True, ex=LOCK_TTL_SECONDS):
        summary.skipped = True
        return summary

    try:
        await _run_sync(connection_id, user_id, psu, summary)
    finally:
        await redis_client.delete(_lock_key(connection_id))

    if scheduled and summary.error_code:
        ttl = (
            _ATTEMPT_TTL_AFTER_RATE_LIMIT
            if summary.error_code == "rate_limited"
            else _ATTEMPT_TTL_AFTER_TRANSIENT_FAILURE
        )
        await redis_client.set(_attempt_key(connection_id), "1", ex=ttl)
    if scheduled and summary.imported > 0:
        # Sync automatica (utente lontano dall'app): avvisa sul telefono, senza importi.
        await push_service.notify_new_transactions(user_id, summary.imported)
    return summary


async def _set_connection_state(
    user_id: uuid.UUID,
    connection_id: uuid.UUID,
    *,
    status: str | None = None,
    last_error: str | None,
    touch_sync: bool = False,
) -> None:
    async with rls_session(user_id) as db:
        connection = await db.get(BankConnection, connection_id)
        if connection is None:
            return
        if status is not None:
            connection.status = status
        connection.last_error = last_error
        if touch_sync:
            connection.last_sync_at = datetime.now(UTC)
        await db.commit()


async def _run_sync(
    connection_id: uuid.UUID, user_id: uuid.UUID, psu: PsuContext | None, summary: SyncSummary
) -> None:
    async with rls_session(user_id) as db:
        connection = await db.get(BankConnection, connection_id)
        if connection is None or connection.owner_user_id != user_id or connection.status != "active":
            summary.skipped = True
            return
        # Un utente disattivato non sincronizza piu': il job non passa dal login
        # (che controlla `is_active`), quindi lo controlla da se'.
        owner = await db.get(User, user_id)
        if owner is None or not owner.is_active:
            summary.skipped = True
            return
        workspace_id = connection.workspace_id
        aspsp_name = connection.aspsp_name
        if connection.valid_until is not None and connection.valid_until <= datetime.now(UTC):
            connection.status = "expired"
            connection.last_error = "authorization_expired"
            summary.error_code = "authorization_expired"
            await db.commit()
            return
        credential = await open_banking_service.get_credential(db, user_id)
        session_id = decrypt_secret(connection.session_id_encrypted) if connection.session_id_encrypted else None
        accounts = [
            _AccountJob(a.id, a.provider_account_uid, a.financial_account_id, a.last_booked_date, a.iban)
            for a in (
                await db.scalars(
                    select(BankConnectionAccount).where(
                        BankConnectionAccount.connection_id == connection_id,
                        BankConnectionAccount.enabled.is_(True),
                        BankConnectionAccount.financial_account_id.is_not(None),
                    )
                )
            ).all()
        ]
    if credential is None or session_id is None:
        summary.error_code = "credentials_missing"
        await _set_connection_state(user_id, connection_id, last_error="credentials_missing")
        return
    try:
        connector = open_banking_service.build_connector(credential)
    except OpenBankingError as exc:
        summary.error_code = exc.code or "provider_error"
        await _set_connection_state(user_id, connection_id, last_error=summary.error_code)
        return

    reconcile = timedelta(days=get_settings().open_banking_reconcile_days)
    for account in accounts:
        try:
            date_from = (account.last_booked_date - reconcile) if account.last_booked_date else None
            fetched = await connector.get_transactions(
                account.provider_uid, date_from=date_from, longest=account.last_booked_date is None, psu=psu
            )
        except AuthorizationExpiredError:
            summary.error_code = "authorization_expired"
            await _set_connection_state(
                user_id, connection_id, status="expired", last_error="authorization_expired"
            )
            return
        except RateLimitedError:
            summary.error_code = "rate_limited"
            break
        except OpenBankingAuthError:
            summary.error_code = "auth_failed"
            break
        except ProviderUnavailableError:
            summary.error_code = "provider_unavailable"
            continue
        except OpenBankingError as exc:
            logger.warning("sync conto fallita (%s, http=%s)", exc.code, exc.http_status)
            summary.error_code = "provider_error"
            continue

        try:
            await _persist_account(user_id, workspace_id, aspsp_name, account, fetched, summary)
        except Exception:
            # Un conto che fallisce non blocca gli altri; mai dati finanziari nel log.
            logger.exception("sync: persistenza fallita per la connessione %s", connection_id)
            summary.error_code = "persist_failed"

    await _set_connection_state(
        user_id,
        connection_id,
        last_error=summary.error_code,
        touch_sync=summary.error_code is None,
    )


async def _persist_account(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    aspsp_name: str,
    account: _AccountJob,
    fetched: list[NormalizedTransaction],
    summary: SyncSummary,
) -> None:
    # Import locale: la pipeline di persistenza vive nel modulo del job di import.
    from app.worker.jobs.import_job import _insert_transactions_and_complete

    now = datetime.now(UTC)
    rows: list[ParsedRow] = []
    max_booked: date | None = None
    if fetched:
        async with rls_session(user_id) as db:
            known = await _existing_external_ids(
                db,
                workspace_id,
                account.financial_account_id,
                [t.external_id for t in fetched if t.external_id],
            )
            seen: set[str] = set()
            for tx in fetched:
                booked = tx.booking_date or tx.transaction_date
                max_booked = booked if max_booked is None or booked > max_booked else max_booked
                if tx.external_id:
                    if tx.external_id in known or tx.external_id in seen:
                        summary.duplicates += 1
                        continue
                    seen.add(tx.external_id)
                row = to_parsed_row(tx)
                if tx.counterparty_iban or tx.counterparty_name:
                    counterparty = TransferCounterparty(name=tx.counterparty_name, iban=tx.counterparty_iban)
                    if await is_internal_transfer(db, workspace_id, counterparty):
                        row.transaction_type = "transfer"
                rows.append(row)

    import_id: uuid.UUID | None = None
    if rows:
        import_id = uuid.uuid4()
        async with rls_session(user_id) as db:
            db.add(
                Import(
                    id=import_id,
                    workspace_id=workspace_id,
                    financial_account_id=account.financial_account_id,
                    created_by_user_id=user_id,
                    file_type="open_banking",
                    status="parsing",
                    filename=f"Open Banking - {aspsp_name}"[:200],
                    file_hash=hashlib.sha256(import_id.bytes).hexdigest(),
                    file_size=0,
                )
            )
            await db.commit()
        await _insert_transactions_and_complete(
            import_id, user_id, workspace_id, account.financial_account_id, rows
        )

    async with rls_session(user_id) as db:
        stored = await db.get(BankConnectionAccount, account.account_id)
        if stored is None:
            return
        if import_id is not None:
            import_row = await db.get(Import, import_id)
            if import_row is not None:
                stored.transactions_imported += import_row.transactions_imported
                summary.imported += import_row.transactions_imported
                summary.duplicates += import_row.transactions_duplicate
                summary.review_pending += import_row.transactions_review_pending
        if max_booked is not None and (stored.last_booked_date is None or max_booked > stored.last_booked_date):
            stored.last_booked_date = max_booked
        stored.last_sync_at = now
        await db.commit()
    summary.accounts_synced += 1

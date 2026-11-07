"""Sincronizzazione dei movimenti da una connessione Open Banking.

Idempotente: ogni sync rilegge i movimenti dalla data dell'ultimo importato
meno una finestra di riconciliazione, scarta quelli gia' presenti e passa i
restanti dalla pipeline unica di import (dedup a fingerprint con REVIEW per i
casi ambigui, classificazione, riconoscimento trasferimenti): un `Import` con
`file_type='open_banking'` per ogni conto con movimenti nuovi.

Garanzie (vedi `.claude/memoria/task-open-banking.md`):
- il cursore (`last_booked_date`) avanza SOLO a persistenza confermata e mai oltre
  oggi; una lettura parziale o una persistenza saltata non lo muovono;
- `external_id` e' una prova di duplicato solo se coincidono anche importo, valuta
  e data (entro tolleranza): un id riusato con contenuto diverso non scarta il
  movimento in silenzio;
- i movimenti eliminati a mano (tombstone) e quelli con una review gia' presente
  non tornano a ogni sync;
- ogni conto ha le proprie statistiche (`last_sync_stats`): SOLO conteggi.

Identita' RLS: il job gira con l'utente proprietario della connessione, mai con
BYPASSRLS. Nessuna query RLS dopo un commit nella stessa sessione: ogni blocco
apre la propria `rls_session` e fa un solo commit.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.redis import redis_client
from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.open_banking import BankConnection, BankConnectionAccount, BankTransactionTombstone
from app.models.transaction import Transaction
from app.models.transaction_review_item import TransactionReviewItem
from app.models.user import User
from app.openbanking.base import FetchStats, NormalizedTransaction, PsuContext
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
from app.services.transaction_type_mapping_service import OPEN_BANKING_PARSER_TYPE, resolve_transaction_type
from app.services.transfer_recognition import is_internal_transfer

logger = logging.getLogger("lumio.bank_sync")

LOCK_TTL_SECONDS = 900
MANUAL_SYNC_COOLDOWN_SECONDS = 30
# Il limite di molte banche e' 4 letture al giorno senza utente presente.
MIN_INTERVAL_HOURS = 6
_ATTEMPT_TTL_AFTER_TRANSIENT_FAILURE = 3600
_ATTEMPT_TTL_AFTER_RATE_LIMIT = 12 * 3600
# Errori che richiedono l'intervento dell'utente: inutile riprovare presto.
_ATTEMPT_TTL_BY_ERROR = {
    "rate_limited": _ATTEMPT_TTL_AFTER_RATE_LIMIT,
    "auth_failed": 12 * 3600,
    "credentials_missing": 12 * 3600,
    "authorization_expired": 24 * 3600,
}
_RATE_LIMIT_FLAG_TTL = 12 * 3600
_EXTERNAL_ID_CHUNK = 500
# Stesso id + stesso importo/valuta: e' lo stesso movimento anche se la banca ne
# sposta di qualche giorno la data contabile.
_ID_DATE_TOLERANCE_DAYS = 5
_WRONG_PERIOD_CODE = "WRONG_TRANSACTIONS_PERIOD"
_PREFERRED_BALANCE_TYPES = ("CLBD", "ITAV", "XPCD", "CLAV")


def _lock_key(connection_id: uuid.UUID) -> str:
    return f"bank_sync:lock:{connection_id}"


def _attempt_key(connection_id: uuid.UUID) -> str:
    return f"bank_sync:attempt:{connection_id}"


def _rate_limit_key(connection_id: uuid.UUID) -> str:
    return f"bank_sync:ratelimited:{connection_id}"


def effective_interval_seconds() -> int:
    hours = max(MIN_INTERVAL_HOURS, get_settings().open_banking_sync_interval_hours)
    return hours * 3600


async def is_sync_running(connection_id: uuid.UUID) -> bool:
    return bool(await redis_client.exists(_lock_key(connection_id)))


async def is_rate_limited(connection_id: uuid.UUID) -> bool:
    """True se la banca ha risposto 429 di recente: leggere ancora peggiora."""
    return bool(await redis_client.exists(_rate_limit_key(connection_id)))


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

    def note_error(self, code: str) -> None:
        """Il primo errore vince: e' quello che ha causato il resto."""
        if self.error_code is None:
            self.error_code = code


class SyncPersistError(Exception):
    """La persistenza dei movimenti non e' avvenuta: il cursore non deve avanzare."""


def source_label(tx: NormalizedTransaction) -> str | None:
    """Etichetta grezza del tipo di movimento (chiave delle mappature utente):
    descrizione della banca e, se c'e', il codice ISO 20022."""
    description, code = tx.bank_transaction_code, tx.bank_code
    if description and code:
        return f"{description} ({code})"[:200]
    value = description or code
    return value[:200] if value else None


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
        # Solo il segno: la mappatura piu' specifica spetta alle regole/AI, alle
        # mappature per etichetta e alle correzioni dell'utente (regola del
        # progetto sui tipi).
        transaction_type="expense" if is_debit else "income",
        source_type_raw=source_label(tx),
        reference=tx.reference,
        balance_after=tx.balance_after,
        counterparty_name=tx.counterparty_name,
        counterparty_iban=tx.counterparty_iban,
        external_id=tx.external_id,
    )


# ---- confronto dei movimenti -------------------------------------------------

_Signature = tuple[Decimal, str, date]


def _signature(amount: Decimal, currency: str, day: date) -> _Signature:
    return (amount.quantize(Decimal("0.01")), currency.strip().upper(), day)


def _same_movement(a: _Signature, b: _Signature) -> bool:
    return a[0] == b[0] and a[1] == b[1] and abs((a[2] - b[2]).days) <= _ID_DATE_TOLERANCE_DAYS


async def _known_by_external_id(
    db, workspace_id, financial_account_id, external_ids: list[str]
) -> dict[str, list[_Signature]]:
    found: dict[str, list[_Signature]] = {}
    for start in range(0, len(external_ids), _EXTERNAL_ID_CHUNK):
        chunk = external_ids[start : start + _EXTERNAL_ID_CHUNK]
        rows = await db.execute(
            select(
                Transaction.external_id, Transaction.amount, Transaction.currency, Transaction.transaction_date
            ).where(
                Transaction.workspace_id == workspace_id,
                Transaction.financial_account_id == financial_account_id,
                Transaction.external_id.in_(chunk),
            )
        )
        for external_id, amount, currency, day in rows.all():
            found.setdefault(external_id, []).append(_signature(amount, currency, day))
    return found


async def _tombstoned_ids(db, workspace_id, financial_account_id, external_ids: list[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(external_ids), _EXTERNAL_ID_CHUNK):
        chunk = external_ids[start : start + _EXTERNAL_ID_CHUNK]
        rows = await db.scalars(
            select(BankTransactionTombstone.external_id).where(
                BankTransactionTombstone.workspace_id == workspace_id,
                BankTransactionTombstone.financial_account_id == financial_account_id,
                BankTransactionTombstone.external_id.in_(chunk),
            )
        )
        found.update(rows.all())
    return found


async def _reviewed_ids(db, workspace_id, financial_account_id, external_ids: list[str]) -> set[str]:
    """Id per cui esiste gia' una review (pendente o decisa): non si riaccodano."""
    found: set[str] = set()
    for start in range(0, len(external_ids), _EXTERNAL_ID_CHUNK):
        chunk = external_ids[start : start + _EXTERNAL_ID_CHUNK]
        rows = await db.scalars(
            select(TransactionReviewItem.external_id).where(
                TransactionReviewItem.workspace_id == workspace_id,
                TransactionReviewItem.financial_account_id == financial_account_id,
                TransactionReviewItem.external_id.in_(chunk),
            )
        )
        found.update(rows.all())
    return found


def count_balance_gaps(transactions: list[NormalizedTransaction]) -> tuple[int, int]:
    """Controllo di continuita' sul saldo dopo movimento, senza dipendere
    dall'ordine in cui la banca restituisce i movimenti: il saldo precedente di
    ogni riga (`balance_after - amount`) deve comparire come saldo di un'altra
    riga; l'unica eccezione e' la piu' vecchia della finestra. Ritorna
    (righe con saldo, salti sospetti). Con meno di 3 righe il controllo non e' significativo."""
    rows = [t for t in transactions if t.balance_after is not None]
    if len(rows) < 3:
        return len(rows), 0
    balances = Counter(t.balance_after.quantize(Decimal("0.01")) for t in rows)
    unmatched = sum(1 for t in rows if (t.balance_after - t.amount).quantize(Decimal("0.01")) not in balances)
    return len(rows), max(0, unmatched - 1)


@dataclass
class _AccountJob:
    account_id: uuid.UUID
    provider_uid: str
    financial_account_id: uuid.UUID
    last_booked_date: date | None
    iban: str | None
    currency: str | None = None


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

    attempt_taken = False
    if scheduled:
        if not await redis_client.set(_attempt_key(connection_id), "1", nx=True, ex=interval):
            summary.skipped = True
            return summary
        attempt_taken = True
    if not await redis_client.set(_lock_key(connection_id), "1", nx=True, ex=LOCK_TTL_SECONDS):
        summary.skipped = True
        if attempt_taken:
            # Una sync saltata non e' un tentativo: non deve consumare l'intervallo.
            await redis_client.delete(_attempt_key(connection_id))
        return summary

    try:
        await _run_sync(connection_id, user_id, psu, summary)
    finally:
        await redis_client.delete(_lock_key(connection_id))

    if scheduled and summary.skipped:
        await redis_client.delete(_attempt_key(connection_id))
    elif scheduled and summary.error_code:
        ttl = _ATTEMPT_TTL_BY_ERROR.get(summary.error_code, _ATTEMPT_TTL_AFTER_TRANSIENT_FAILURE)
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


async def _store_account_diagnostics(
    user_id: uuid.UUID, account_id: uuid.UUID, stats: dict, *, balance_snapshot: dict | None = None
) -> None:
    async with rls_session(user_id) as db:
        stored = await db.get(BankConnectionAccount, account_id)
        if stored is None:
            return
        stored.last_sync_stats = stats
        if balance_snapshot is not None:
            stored.balance_snapshot = balance_snapshot
        await db.commit()


async def _fetch_account(
    connector, account: _AccountJob, reconcile: timedelta, psu: PsuContext | None
) -> tuple[list[NormalizedTransaction], FetchStats]:
    longest = account.last_booked_date is None
    date_from = None if longest else account.last_booked_date - reconcile
    stats = FetchStats()
    try:
        fetched = await connector.get_transactions(
            account.provider_uid, date_from=date_from, longest=longest, psu=psu, stats=stats
        )
    except OpenBankingError as exc:
        if exc.code != _WRONG_PERIOD_CODE or longest:
            raise
        # La banca rifiuta la finestra richiesta (troppo vecchia): rilettura completa;
        # il dedup assorbe cio' che esiste gia'.
        stats = FetchStats()
        fetched = await connector.get_transactions(
            account.provider_uid, longest=True, psu=psu, stats=stats
        )
    return fetched, stats


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
            _AccountJob(
                a.id, a.provider_account_uid, a.financial_account_id, a.last_booked_date, a.iban, a.currency
            )
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
        fetch_stats = FetchStats()
        try:
            fetched, fetch_stats = await _fetch_account(connector, account, reconcile, psu)
        except AuthorizationExpiredError:
            summary.error_code = "authorization_expired"
            await _set_connection_state(
                user_id, connection_id, status="expired", last_error="authorization_expired"
            )
            return
        except RateLimitedError:
            summary.note_error("rate_limited")
            await redis_client.set(_rate_limit_key(connection_id), "1", ex=_RATE_LIMIT_FLAG_TTL)
            await _store_account_diagnostics(user_id, account.account_id, {"error": "rate_limited"})
            break
        except OpenBankingAuthError as exc:
            summary.note_error("auth_failed")
            await _store_account_diagnostics(user_id, account.account_id, {"error": "auth_failed"})
            if exc.http_status == 401:
                # Credenziali dell'applicazione: vale per tutti i conti.
                break
            continue  # 403 su un conto: gli altri possono funzionare
        except ProviderUnavailableError:
            summary.note_error("provider_unavailable")
            await _store_account_diagnostics(user_id, account.account_id, {"error": "provider_unavailable"})
            continue
        except OpenBankingError as exc:
            logger.warning("sync conto fallita (%s, http=%s)", exc.code, exc.http_status)
            code = "incomplete_fetch" if exc.code == "incomplete_fetch" else "provider_error"
            summary.note_error(code)
            await _store_account_diagnostics(
                user_id, account.account_id, {"error": code, "fetch": fetch_stats.as_dict()}
            )
            continue
        except Exception:
            # Risposta imprevista che il connettore non sa leggere: il conto e' saltato,
            # gli altri continuano. Mai dati finanziari nel log.
            logger.exception("sync: lettura fallita per la connessione %s", connection_id)
            summary.note_error("parse_error")
            await _store_account_diagnostics(user_id, account.account_id, {"error": "parse_error"})
            continue

        try:
            await _persist_account(user_id, workspace_id, aspsp_name, account, fetched, summary, fetch_stats)
        except Exception:
            logger.exception("sync: persistenza fallita per la connessione %s", connection_id)
            summary.note_error("persist_failed")
            await _store_account_diagnostics(
                user_id, account.account_id, {"error": "persist_failed", "fetch": fetch_stats.as_dict()}
            )
            continue
        await _refresh_balance_snapshot(user_id, connector, account, fetched, psu)

    await _set_connection_state(
        user_id,
        connection_id,
        last_error=summary.error_code,
        touch_sync=summary.error_code is None,
    )


async def _refresh_balance_snapshot(
    user_id: uuid.UUID, connector, account: _AccountJob, fetched: list[NormalizedTransaction], psu: PsuContext | None
) -> None:
    """Saldo dichiarato dalla banca + controllo di continuita'. Non critico: un
    errore qui non fa fallire la sync."""
    rows_with_balance, gaps = count_balance_gaps(fetched)
    snapshot: dict = {
        "at": datetime.now(UTC).isoformat(),
        "rows_with_balance": rows_with_balance,
        "continuity_gaps": gaps,
    }
    try:
        balances = await connector.get_balances(account.provider_uid, psu=psu)
    except Exception:
        balances = []
    chosen = None
    for wanted in _PREFERRED_BALANCE_TYPES:
        chosen = next((b for b in balances if b.balance_type.upper() == wanted), None)
        if chosen is not None:
            break
    if chosen is None and balances:
        chosen = balances[0]
    if chosen is not None:
        snapshot.update(type=chosen.balance_type, amount=str(chosen.amount), currency=chosen.currency)
    try:
        async with rls_session(user_id) as db:
            stored = await db.get(BankConnectionAccount, account.account_id)
            if stored is not None:
                stored.balance_snapshot = snapshot
                await db.commit()
    except Exception:
        logger.warning("sync: snapshot del saldo non salvato", exc_info=True)


async def _persist_account(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    aspsp_name: str,
    account: _AccountJob,
    fetched: list[NormalizedTransaction],
    summary: SyncSummary,
    fetch_stats: FetchStats,
) -> None:
    # Import locale: la pipeline di persistenza vive nel modulo del job di import.
    from app.worker.jobs.import_job import _insert_transactions_and_complete

    now = datetime.now(UTC)
    rows: list[ParsedRow] = []
    max_booked: date | None = None
    counts: Counter[str] = Counter()
    account_currency = (account.currency or "").strip().upper() or None

    if fetched:
        async with rls_session(user_id) as db:
            ids = [t.external_id for t in fetched if t.external_id]
            known = await _known_by_external_id(db, workspace_id, account.financial_account_id, ids)
            tombstoned = await _tombstoned_ids(db, workspace_id, account.financial_account_id, ids)
            reviewed = await _reviewed_ids(db, workspace_id, account.financial_account_id, ids)
            seen: dict[str, list[_Signature]] = {}
            for tx in fetched:
                booked = tx.booking_date or tx.transaction_date
                max_booked = booked if max_booked is None or booked > max_booked else max_booked
                if account_currency and tx.currency != account_currency:
                    # Valuta diversa da quella del conto: non si importa, si segnala.
                    counts["foreign_currency"] += 1
                    continue
                sig = _signature(tx.amount, tx.currency, tx.transaction_date)
                if tx.external_id:
                    if tx.external_id in tombstoned:
                        counts["tombstoned"] += 1
                        continue
                    if tx.external_id in reviewed:
                        counts["review_known"] += 1
                        continue
                    if any(_same_movement(sig, p) for p in known.get(tx.external_id, [])):
                        counts["known_duplicate"] += 1
                        summary.duplicates += 1
                        continue
                    if any(_same_movement(sig, p) for p in seen.get(tx.external_id, [])):
                        counts["repeated_in_batch"] += 1
                        summary.duplicates += 1
                        continue
                    if known.get(tx.external_id) or seen.get(tx.external_id):
                        # Stesso id ma contenuto diverso (batch di regolamento, id
                        # riusati): e' un movimento distinto, va col fingerprint.
                        counts["id_reused_distinct"] += 1
                    seen.setdefault(tx.external_id, []).append(sig)
                row = to_parsed_row(tx)
                if tx.counterparty_iban or tx.counterparty_name:
                    counterparty = TransferCounterparty(name=tx.counterparty_name, iban=tx.counterparty_iban)
                    if await is_internal_transfer(db, workspace_id, counterparty):
                        row.transaction_type = "transfer"
                # Mappatura per etichetta della banca scelta dall'utente (se c'e').
                row.transaction_type = await resolve_transaction_type(
                    db, workspace_id, OPEN_BANKING_PARSER_TYPE, row.source_type_raw, row.transaction_type
                )
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
        persisted = await _insert_transactions_and_complete(
            import_id, user_id, workspace_id, account.financial_account_id, rows
        )
        if not persisted:
            # L'import non era piu' in `parsing` (annullato o eliminato): nulla e'
            # stato scritto, quindi il cursore NON deve avanzare.
            raise SyncPersistError("import non piu' in parsing")

    # Mai oltre oggi: una data contabile futura (errore della banca) farebbe
    # saltare per sempre i movimenti dei giorni successivi.
    cursor_target = min(max_booked, now.date()) if max_booked is not None else None

    async with rls_session(user_id) as db:
        stored = await db.get(BankConnectionAccount, account.account_id)
        if stored is None:
            return
        advance = True
        imported = duplicate = review_pending = 0
        if import_id is not None:
            import_row = await db.get(Import, import_id)
            if import_row is None:
                # Import eliminato mentre la sync finiva: la sua eliminazione ha gia'
                # azzerato il cursore, non va rimesso avanti.
                advance = False
            else:
                imported = import_row.transactions_imported
                duplicate = import_row.transactions_duplicate
                review_pending = import_row.transactions_review_pending
                stored.transactions_imported += imported
                summary.imported += imported
                summary.duplicates += duplicate
                summary.review_pending += review_pending
        if advance and cursor_target is not None and (
            stored.last_booked_date is None or cursor_target > stored.last_booked_date
        ):
            stored.last_booked_date = cursor_target
        stored.last_sync_at = now
        stored.last_sync_stats = {
            "fetch": fetch_stats.as_dict(),
            "persist": {
                **dict(counts),
                "imported": imported,
                "duplicate_by_fingerprint": duplicate,
                "in_review": review_pending,
            },
            "at": now.isoformat(),
        }
        await db.commit()
    summary.accounts_synced += 1

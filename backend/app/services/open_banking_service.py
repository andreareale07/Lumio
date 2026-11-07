"""Logica DB-aware dell'integrazione Open Banking.

Tutte le funzioni lavorano sulle tabelle owner-only (`open_banking_credentials`,
`bank_connections`, `bank_connection_accounts`): la RLS e' il secondo livello,
ma ogni query filtra comunque esplicitamente per `owner_user_id` (regola n.1
di CLAUDE.md: mai fidarsi di un solo livello).

Nessuna funzione fa commit: il chiamante decide il confine di transazione (un
solo commit a fine richiesta, `SET LOCAL` scade al commit).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.financial_account import FinancialAccount
from app.models.import_ import Import
from app.models.open_banking import BankConnection, BankConnectionAccount, OpenBankingCredential
from app.openbanking import PROVIDER_ENABLE_BANKING, get_connector
from app.openbanking.base import BankConnector, ConnectionSession
from app.openbanking.errors import OpenBankingError
from app.openbanking.keys import generate_keypair
from app.schemas.accounts import FinancialAccountCreate
from app.services.account_service import create_financial_account
from app.services.iban_utils import normalize_iban
from app.services.import_deletion import delete_import_transactions

# Soglia oltre la quale la UI propone di rinnovare il consenso.
EXPIRING_SOON_DAYS = 7
# Massimo consenso richiesto quando la banca non dichiara un limite (180 giorni
# e' il massimo PSD2 tipico per il consenso AIS).
DEFAULT_CONSENT_DAYS = 180
STALE_PENDING_AFTER = timedelta(hours=1)

_ACCOUNT_TYPE_BY_CASH_TYPE = {"SVGS": "savings", "CARD": "credit_card", "CACC": "checking"}


def mask_iban(iban: str | None) -> str | None:
    if not iban:
        return None
    compact = iban.replace(" ", "")
    if len(compact) <= 8:
        return compact
    return f"{compact[:4]}••••{compact[-4:]}"


# ---- credenziali ---------------------------------------------------------


async def get_credential(db: AsyncSession, user_id: uuid.UUID) -> OpenBankingCredential | None:
    return await db.scalar(
        select(OpenBankingCredential).where(
            OpenBankingCredential.owner_user_id == user_id,
            OpenBankingCredential.provider == PROVIDER_ENABLE_BANKING,
        )
    )


async def create_credential(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> OpenBankingCredential:
    private_pem, certificate_pem = generate_keypair()
    credential = OpenBankingCredential(
        workspace_id=workspace_id,
        owner_user_id=user_id,
        provider=PROVIDER_ENABLE_BANKING,
        private_key_encrypted=encrypt_secret(private_pem),
        certificate_pem=certificate_pem,
    )
    db.add(credential)
    await db.flush()
    return credential


def build_connector(credential: OpenBankingCredential) -> BankConnector:
    """Connettore con le credenziali dell'utente. Solleva `OpenBankingError`
    se l'app non e' ancora configurata o la chiave non e' decifrabile (es.
    `SECRET_KEY` cambiata: l'utente deve rigenerare le credenziali)."""
    if not credential.application_id:
        raise OpenBankingError("Application ID non ancora configurato", code="not_configured")
    private_pem = decrypt_secret(credential.private_key_encrypted)
    if private_pem is None:
        raise OpenBankingError("Chiave non decifrabile: rigenera le credenziali", code="key_unreadable")
    return get_connector(
        credential.provider, application_id=credential.application_id, private_key_pem=private_pem
    )


async def revoke_connection_session(connection: BankConnection, connector: BankConnector) -> bool:
    """Revoca best effort presso il provider. `False` se non riuscita: lo
    scollegamento locale procede comunque (la sessione scade da sola)."""
    if not connection.session_id_encrypted:
        return True
    session_id = decrypt_secret(connection.session_id_encrypted)
    if session_id is None:
        return True
    try:
        await connector.revoke(session_id)
    except OpenBankingError:
        return False
    return True


async def delete_credential(db: AsyncSession, credential: OpenBankingCredential) -> int:
    """Revoca tutte le sessioni dell'utente (best effort) e cancella
    credenziale, connessioni e conti (CASCADE). I movimenti gia' importati
    restano. Ritorna il numero di sessioni che NON si e' riusciti a revocare."""
    connections = (
        await db.scalars(select(BankConnection).where(BankConnection.credential_id == credential.id))
    ).all()
    failed = 0
    if connections:
        try:
            connector = build_connector(credential)
        except OpenBankingError:
            failed = sum(1 for c in connections if c.session_id_encrypted)
        else:
            for connection in connections:
                if not await revoke_connection_session(connection, connector):
                    failed += 1
    await db.delete(credential)
    await db.flush()
    return failed


# ---- connessioni ---------------------------------------------------------


async def purge_stale_pending(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Rimuove le autorizzazioni avviate e mai completate o fallite (utente che
    ha chiuso la pagina della banca, consenso negato): non servono a nulla."""
    cutoff = datetime.now(UTC) - STALE_PENDING_AFTER
    await db.execute(
        delete(BankConnection).where(
            BankConnection.owner_user_id == user_id,
            BankConnection.status.in_(("pending", "error")),
            BankConnection.created_at < cutoff,
        )
    )


def consent_valid_until(maximum_validity_seconds: int | None) -> datetime:
    days = DEFAULT_CONSENT_DAYS
    if maximum_validity_seconds:
        days = min(days, max(1, maximum_validity_seconds // 86400))
    # Un margine di un'ora evita di superare il massimo dichiarato dalla banca
    # per via dei secondi trascorsi tra la richiesta e la risposta.
    return datetime.now(UTC) + timedelta(days=days) - timedelta(hours=1)


async def get_connection(
    db: AsyncSession, user_id: uuid.UUID, connection_id: uuid.UUID
) -> BankConnection | None:
    return await db.scalar(
        select(BankConnection).where(
            BankConnection.id == connection_id, BankConnection.owner_user_id == user_id
        )
    )


async def list_connections(db: AsyncSession, user_id: uuid.UUID) -> list[BankConnection]:
    return list(
        (
            await db.scalars(
                select(BankConnection)
                .where(BankConnection.owner_user_id == user_id, BankConnection.status.not_in(("pending", "error")))
                .order_by(BankConnection.created_at)
            )
        ).all()
    )


async def list_connection_accounts(
    db: AsyncSession, user_id: uuid.UUID, connection_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[BankConnectionAccount]]:
    grouped: dict[uuid.UUID, list[BankConnectionAccount]] = {cid: [] for cid in connection_ids}
    if not connection_ids:
        return grouped
    rows = await db.scalars(
        select(BankConnectionAccount)
        .where(
            BankConnectionAccount.owner_user_id == user_id,
            BankConnectionAccount.connection_id.in_(connection_ids),
        )
        .order_by(BankConnectionAccount.created_at, BankConnectionAccount.name)
    )
    for row in rows:
        grouped[row.connection_id].append(row)
    return grouped


async def apply_session(
    db: AsyncSession,
    connection: BankConnection,
    session: ConnectionSession,
    session_id_encrypted: str,
) -> None:
    """Attiva la connessione con la sessione appena autorizzata e registra i
    conti esposti. Se esiste una connessione precedente (rinnovo del consenso)
    verso la stessa banca, ne eredita abbinamenti e cursore per IBAN, cosi'
    il rinnovo non obbliga a rifare la configurazione ne' a reimportare tutto."""
    connection.status = "active"
    connection.session_id_encrypted = session_id_encrypted
    connection.valid_until = session.valid_until
    connection.last_error = None
    connection.state_nonce_hash = None

    previous = (
        await db.scalars(
            select(BankConnection).where(
                BankConnection.owner_user_id == connection.owner_user_id,
                BankConnection.credential_id == connection.credential_id,
                BankConnection.aspsp_name == connection.aspsp_name,
                BankConnection.aspsp_country == connection.aspsp_country,
                BankConnection.id != connection.id,
                BankConnection.status != "pending",
            ).order_by(BankConnection.created_at.desc(), BankConnection.id)
        )
    ).all()
    # Chiave = IBAN normalizzato (maiuscole, senza spazi): la banca puo' cambiare
    # formato tra un consenso e l'altro. Ordine deterministico: vince la
    # connessione piu' recente.
    previous_by_iban: dict[str, BankConnectionAccount] = {}
    for old in previous:
        for old_account in sorted(await list_accounts_of(db, old.id), key=lambda a: (a.created_at, a.id)):
            if old_account.iban:
                previous_by_iban.setdefault(normalize_iban(old_account.iban), old_account)

    for provider_account in session.accounts:
        inherited = (
            previous_by_iban.get(normalize_iban(provider_account.iban)) if provider_account.iban else None
        )
        db.add(
            BankConnectionAccount(
                workspace_id=connection.workspace_id,
                owner_user_id=connection.owner_user_id,
                connection_id=connection.id,
                provider_account_uid=provider_account.uid,
                iban=provider_account.iban,
                name=provider_account.name,
                product=provider_account.product,
                currency=provider_account.currency,
                cash_account_type=provider_account.cash_account_type,
                financial_account_id=inherited.financial_account_id if inherited else None,
                enabled=inherited.enabled if inherited else False,
                last_booked_date=inherited.last_booked_date if inherited else None,
                transactions_imported=inherited.transactions_imported if inherited else 0,
            )
        )
    await db.flush()


async def list_accounts_of(db: AsyncSession, connection_id: uuid.UUID) -> list[BankConnectionAccount]:
    return list(
        (
            await db.scalars(
                select(BankConnectionAccount).where(BankConnectionAccount.connection_id == connection_id)
            )
        ).all()
    )


async def retire_previous_connections(
    db: AsyncSession, connection: BankConnection, connector: BankConnector
) -> None:
    """Dopo un rinnovo riuscito: revoca e rimuove le connessioni precedenti
    verso la stessa banca (molte banche italiane ammettono un solo consenso
    attivo per applicazione e utente, quindi comunque gia' invalidato)."""
    previous = (
        await db.scalars(
            select(BankConnection).where(
                BankConnection.owner_user_id == connection.owner_user_id,
                BankConnection.credential_id == connection.credential_id,
                BankConnection.aspsp_name == connection.aspsp_name,
                BankConnection.aspsp_country == connection.aspsp_country,
                BankConnection.id != connection.id,
                BankConnection.status != "pending",
            )
        )
    ).all()
    for old in previous:
        await revoke_connection_session(old, connector)
        await db.delete(old)
    await db.flush()


# ---- abbinamento conti -----------------------------------------------------


def account_type_for(cash_account_type: str | None) -> str:
    return _ACCOUNT_TYPE_BY_CASH_TYPE.get((cash_account_type or "").upper(), "checking")


async def create_lumio_account_from_bank_account(
    db: AsyncSession, workspace_id: uuid.UUID, connection: BankConnection, account: BankConnectionAccount
) -> FinancialAccount:
    base_name = account.name or account.product or connection.aspsp_name
    name = base_name if base_name.lower().startswith(connection.aspsp_name.lower()) else (
        f"{connection.aspsp_name} - {base_name}"
    )
    payload = FinancialAccountCreate(
        name=name[:200],
        account_type=account_type_for(account.cash_account_type),
        currency=(account.currency or "EUR").upper(),
        iban=account.iban,
        account_identifier_masked=mask_iban(account.iban),
    )
    return await create_financial_account(db, workspace_id, payload)


# ---- eliminazione dei dati importati ----------------------------------------


async def delete_connection_imported_data(
    db: AsyncSession, workspace_id: uuid.UUID, connection: BankConnection
) -> int:
    """Elimina i movimenti importati da questa banca: quelli degli `Import` di
    tipo 'open_banking' sui conti Lumio abbinati ai suoi conti. Mai i movimenti
    arrivati da PDF o CSV, nemmeno sullo stesso conto Lumio, e mai quelli
    inseriti a mano. Stessa regola di `DELETE /imports/{id}` (dipendenze
    eliminate a ritroso, posizioni ricalcolate). Non fa commit.

    Solleva 409 se un import e' ancora in elaborazione: come per l'eliminazione
    di un import, non si cancella sotto i piedi di un job in corso.
    Ritorna il numero di transazioni eliminate."""
    financial_account_ids = [
        a.financial_account_id
        for a in await list_accounts_of(db, connection.id)
        if a.financial_account_id is not None
    ]
    if not financial_account_ids:
        return 0
    imports = (
        await db.scalars(
            select(Import).where(
                Import.workspace_id == workspace_id,
                Import.file_type == "open_banking",
                Import.financial_account_id.in_(financial_account_ids),
            )
        )
    ).all()
    if any(
        i.status in ("processing", "parsing") or i.ai_classification_status == "running" for i in imports
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Importazione in corso: attendi il completamento prima di eliminare i movimenti",
        )
    deleted = 0
    for import_row in imports:
        deleted += await delete_import_transactions(db, workspace_id, import_row.id)
        await db.delete(import_row)
    await db.flush()
    return deleted

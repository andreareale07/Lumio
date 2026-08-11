"""Riconoscimento dei trasferimenti interni (SPEC §37: "escludere
correttamente i trasferimenti interni" dal cash flow) — milestone 09.5b.

Prima di questo modulo, `transaction_type='transfer'` era assegnato solo a
mano dall'utente (o via un override di M09.5), senza nessuna verifica che
il bonifico fosse davvero verso un conto proprio del workspace — la SPEC
richiede di escluderli "correttamente", non di fidarsi ciecamente
dell'etichetta. Qui si decide, data la controparte estratta dalla
descrizione (`TransferCounterparty`, vedi `app/parsers/base.py`), se e'
un conto/persona del workspace stesso (household, non solo chi ha
importato — vedi `is_internal_transfer`).

Priorita' IBAN su nominativo: un IBAN che combacia esattamente con un
conto registrato nel workspace e' la prova piu' forte (nessun falso
positivo da omonimia). Se l'IBAN non e' disponibile (sulla riga o sul
conto — la maggior parte degli utenti non l'avra' compilato da subito) si
ricade sul nominativo, confrontato con TUTTI i membri del workspace, non
solo il proprietario del conto importato: un bonifico tra il conto di un
utente e quello del/la partner nello stesso workspace resta interno.
"""
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_parser import BankParser as BankParserRow
from app.models.financial_account import FinancialAccount
from app.models.financial_account_iban_history import FinancialAccountIbanHistory
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.parsers import get_parser
from app.parsers.base import TransferCounterparty


def _normalize_iban(iban: str) -> str:
    return iban.strip().upper().replace(" ", "")


def _normalize_name(name: str) -> frozenset[str]:
    """Insieme di token normalizzati (minuscolo, senza accenti, spazi
    collassati) — cosi' "Mario Rossi" combacia con "ROSSI MARIO" o
    "mario  rossi" indipendentemente dall'ordine o dalla formattazione
    usata dalla banca."""
    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return frozenset(without_accents.lower().split())


async def _matches_known_account_iban(db: AsyncSession, workspace_id: uuid.UUID, iban: str) -> bool:
    """Milestone 09.5c: un istituto puo' cambiare l'IBAN di un conto pur
    restando lo stesso conto (es. migrazione DE->IT osservata su Trade
    Republic) — gli estratti conto passati riportano ancora il VECCHIO
    IBAN come controparte. Si controlla quindi sia l'IBAN ATTUALE di ogni
    conto sia tutti quelli storici (`financial_account_iban_history`,
    popolata automaticamente da `app/api/v1/accounts.py`)."""
    target = _normalize_iban(iban)
    current_result = await db.execute(
        select(FinancialAccount.iban).where(
            FinancialAccount.workspace_id == workspace_id,
            FinancialAccount.iban.is_not(None),
        )
    )
    if any(_normalize_iban(row[0]) == target for row in current_result.all()):
        return True

    history_result = await db.execute(
        select(FinancialAccountIbanHistory.iban).where(
            FinancialAccountIbanHistory.workspace_id == workspace_id,
        )
    )
    return any(_normalize_iban(row[0]) == target for row in history_result.all())


async def _matches_workspace_member_name(db: AsyncSession, workspace_id: uuid.UUID, name: str) -> bool:
    target_tokens = _normalize_name(name)
    if not target_tokens:
        return False
    result = await db.execute(
        select(User.display_name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
    )
    return any(_normalize_name(row[0]) == target_tokens for row in result.all())


async def is_internal_transfer(
    db: AsyncSession, workspace_id: uuid.UUID, counterparty: TransferCounterparty
) -> bool:
    """`True` se la controparte del bonifico e' un conto o una persona di
    questo stesso workspace — vedi il docstring di modulo per la priorita'
    IBAN/nominativo. Un IBAN presente che non combacia con nessun conto
    NON esclude il fallback sul nominativo: e' molto piu' probabile che
    l'utente non abbia ancora registrato l'IBAN di quel conto, che non che
    il bonifico sia davvero verso terzi (deciso esplicitamente con
    l'utente)."""
    if counterparty.iban and await _matches_known_account_iban(db, workspace_id, counterparty.iban):
        return True
    if counterparty.name and await _matches_workspace_member_name(db, workspace_id, counterparty.name):
        return True
    return False


async def archive_previous_iban(
    db: AsyncSession, workspace_id: uuid.UUID, financial_account_id: uuid.UUID, previous_iban: str
) -> FinancialAccountIbanHistory:
    """Milestone 09.5c: aggiunge un IBAN storico per un conto — usata sia
    automaticamente PRIMA di sovrascrivere `financial_accounts.iban` con un
    valore diverso (`app/api/v1/accounts.py:update_account`), sia per
    l'aggiunta MANUALE di un IBAN storico gia' noto all'utente
    (`POST /accounts/{id}/iban-history`, utile a chi imposta un conto per
    la prima volta conoscendo gia' un IBAN precedente). Conserva il vecchio
    valore cosi' i bonifici storici che lo referenziano restano
    riconoscibili (vedi `_matches_known_account_iban`). Idempotente: un
    valore gia' storicizzato non viene duplicato, ne torna la riga
    esistente."""
    existing = await db.execute(
        select(FinancialAccountIbanHistory).where(
            FinancialAccountIbanHistory.workspace_id == workspace_id,
            FinancialAccountIbanHistory.financial_account_id == financial_account_id,
            FinancialAccountIbanHistory.iban == previous_iban,
        )
    )
    entry = existing.scalar_one_or_none()
    if entry is not None:
        return entry
    entry = FinancialAccountIbanHistory(
        workspace_id=workspace_id,
        financial_account_id=financial_account_id,
        iban=previous_iban,
    )
    db.add(entry)
    await db.flush()
    return entry


@dataclass
class ReapplyResult:
    updated: int
    skipped: int


async def reapply_internal_transfer_detection(db: AsyncSession, workspace_id: uuid.UUID) -> ReapplyResult:
    """Da richiamare quando l'utente aggiunge/aggiorna l'IBAN di un conto
    (`app/api/v1/accounts.py`) — un IBAN nuovo puo' rendere riconoscibili
    trasferimenti interni gia' importati. Sincrono (stesso principio di
    `investment_backfill.py`/`transaction_type_mapping_service.reapply_mapping`:
    dati a scala personale, non un'operazione lunga da mettere in coda).

    Stessa euristica anti-sovrascrittura di correzioni manuali: si applica
    `transfer` solo se il tipo attuale coincide ancora col default del
    parser per quella riga — altrimenti si assume una correzione manuale e
    si salta."""
    result = await db.execute(
        select(Transaction, BankParserRow.parser_type)
        .join(
            Import,
            and_(Import.id == Transaction.import_id, Import.workspace_id == Transaction.workspace_id),
        )
        .join(BankParserRow, BankParserRow.id == Import.bank_parser_id)
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.transaction_type != "transfer",
        )
    )

    updated = 0
    skipped = 0
    for transaction, parser_type in result.all():
        try:
            parser = get_parser(parser_type)
        except ValueError:
            continue
        counterparty = parser.extract_transfer_counterparty(transaction.description_raw)
        if counterparty is None or not await is_internal_transfer(db, workspace_id, counterparty):
            continue
        default_type = parser.default_transaction_type(transaction.source_type_raw or "", transaction.direction)
        if transaction.transaction_type == default_type:
            transaction.transaction_type = "transfer"
            updated += 1
        else:
            skipped += 1

    return ReapplyResult(updated=updated, skipped=skipped)

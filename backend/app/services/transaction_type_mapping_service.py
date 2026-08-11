"""Milestone 09.5 — override configurabile dall'utente della mappatura
`source_type_raw` -> `transaction_type` di un parser, con rimappatura
retroattiva delle transazioni gia' importate.

Il default HARDCODED del parser (`BankParser.default_transaction_type`,
vedi `app/parsers/base.py`) resta il fallback quando non esiste nessun
override qui, e il punto di riferimento per capire se una transazione
gia' importata e' ancora al default o e' stata corretta a mano: la
rimappatura retroattiva (`reapply_mapping`) NON tocca una transazione il
cui `transaction_type` attuale non coincide col default ricalcolato per
la sua direzione — si assume una correzione manuale dell'utente, che ha
sempre priorita' (CLAUDE.md), e non esiste un flag dedicato per saperlo
con certezza (deciso con l'utente: questa euristica, coerente col
principio gia' usato in `investment_backfill.py`, invece di un flag
nuovo sul modello o una UI di revisione).
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_parser import BankParser as BankParserRow
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.models.transaction_type_mapping import TransactionTypeMapping
from app.parsers import get_parser


@dataclass
class TypeCount:
    transaction_type: str
    count: int


@dataclass
class LabelInfo:
    source_type_raw: str
    total_count: int
    # Tipi REALMENTE presenti oggi sulle transazioni con questa etichetta
    # (puo' avere piu' di una riga: alcuni default del parser dipendono
    # anche dalla direzione, es. "Transazione con carta" -> refund/expense).
    current_types: list[TypeCount]
    override: str | None  # transaction_type salvato, None se nessun override


@dataclass
class ReapplyResult:
    updated: int
    skipped: int


async def list_used_parser_types(db: AsyncSession, workspace_id: uuid.UUID) -> list[str]:
    """Solo i parser REALMENTE usati da almeno un import di questo
    workspace — evita di mostrare in UI sezioni vuote per parser mai
    incontrati."""
    result = await db.execute(
        select(BankParserRow.parser_type)
        .join(Import, Import.bank_parser_id == BankParserRow.id)
        .where(Import.workspace_id == workspace_id)
        .distinct()
    )
    return [row[0] for row in result.all()]


async def list_observed_labels(db: AsyncSession, workspace_id: uuid.UUID, parser_type: str) -> list[LabelInfo]:
    counts_result = await db.execute(
        select(Transaction.source_type_raw, Transaction.transaction_type, func.count().label("n"))
        .join(
            Import,
            and_(Import.id == Transaction.import_id, Import.workspace_id == Transaction.workspace_id),
        )
        .join(BankParserRow, BankParserRow.id == Import.bank_parser_id)
        .where(
            Transaction.workspace_id == workspace_id,
            BankParserRow.parser_type == parser_type,
            Transaction.source_type_raw.is_not(None),
        )
        .group_by(Transaction.source_type_raw, Transaction.transaction_type)
        .order_by(Transaction.source_type_raw)
    )

    by_label: dict[str, list[TypeCount]] = {}
    for source_type_raw, transaction_type, n in counts_result.all():
        by_label.setdefault(source_type_raw, []).append(TypeCount(transaction_type=transaction_type, count=n))

    overrides_result = await db.execute(
        select(TransactionTypeMapping.source_type_raw, TransactionTypeMapping.transaction_type).where(
            TransactionTypeMapping.workspace_id == workspace_id,
            TransactionTypeMapping.parser_type == parser_type,
        )
    )
    overrides = dict(overrides_result.all())

    return [
        LabelInfo(
            source_type_raw=label,
            total_count=sum(tc.count for tc in type_counts),
            current_types=type_counts,
            override=overrides.get(label),
        )
        for label, type_counts in by_label.items()
    ]


async def resolve_transaction_type(
    db: AsyncSession, workspace_id: uuid.UUID, parser_type: str, source_type_raw: str | None, default_type: str
) -> str:
    """Usata al momento dell'import (`app/worker/jobs/import_job.py`): il
    chiamante ha gia' calcolato `default_type` col default hardcoded del
    parser (che dipende anche dalla direzione, non gestita qui) — questa
    funzione lo sovrascrive solo se esiste un override salvato per
    l'etichetta esatta."""
    if not source_type_raw:
        return default_type
    result = await db.execute(
        select(TransactionTypeMapping.transaction_type).where(
            TransactionTypeMapping.workspace_id == workspace_id,
            TransactionTypeMapping.parser_type == parser_type,
            TransactionTypeMapping.source_type_raw == source_type_raw,
        )
    )
    override = result.scalar_one_or_none()
    return override if override is not None else default_type


async def upsert_mapping(
    db: AsyncSession, workspace_id: uuid.UUID, parser_type: str, source_type_raw: str, transaction_type: str
) -> TransactionTypeMapping:
    result = await db.execute(
        select(TransactionTypeMapping).where(
            TransactionTypeMapping.workspace_id == workspace_id,
            TransactionTypeMapping.parser_type == parser_type,
            TransactionTypeMapping.source_type_raw == source_type_raw,
        )
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        mapping = TransactionTypeMapping(
            workspace_id=workspace_id,
            parser_type=parser_type,
            source_type_raw=source_type_raw,
            transaction_type=transaction_type,
        )
        db.add(mapping)
    else:
        mapping.transaction_type = transaction_type
    await db.flush()
    return mapping


async def delete_mapping(db: AsyncSession, workspace_id: uuid.UUID, parser_type: str, source_type_raw: str) -> bool:
    """Torna al default del parser per i FUTURI import. Le transazioni
    gia' rimappate da questo override restano com'erano — nessun rollback
    automatico, stesso principio di non-inventare-storia di `job_runs`."""
    result = await db.execute(
        select(TransactionTypeMapping).where(
            TransactionTypeMapping.workspace_id == workspace_id,
            TransactionTypeMapping.parser_type == parser_type,
            TransactionTypeMapping.source_type_raw == source_type_raw,
        )
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        return False
    await db.delete(mapping)
    return True


async def reapply_mapping(
    db: AsyncSession, workspace_id: uuid.UUID, parser_type: str, source_type_raw: str, new_type: str
) -> ReapplyResult:
    """Rimappatura retroattiva, SINCRONA (dati a scala personale, stesso
    principio di `investment_backfill.py` — non e' "un'operazione lunga"
    da mettere in coda, CLAUDE.md). Per ogni transazione con questa
    etichetta: se il suo tipo attuale coincide col default del parser
    ricalcolato per la SUA direzione, si aggiorna; altrimenti si assume
    una correzione manuale e si salta (vedi docstring di modulo)."""
    parser = get_parser(parser_type)
    result = await db.execute(
        select(Transaction)
        .join(
            Import,
            and_(Import.id == Transaction.import_id, Import.workspace_id == Transaction.workspace_id),
        )
        .join(BankParserRow, BankParserRow.id == Import.bank_parser_id)
        .where(
            Transaction.workspace_id == workspace_id,
            BankParserRow.parser_type == parser_type,
            Transaction.source_type_raw == source_type_raw,
        )
    )
    transactions = result.scalars().all()

    updated = 0
    skipped = 0
    for transaction in transactions:
        default = parser.default_transaction_type(source_type_raw, transaction.direction)
        if transaction.transaction_type == default:
            transaction.transaction_type = new_type
            updated += 1
        else:
            skipped += 1

    return ReapplyResult(updated=updated, skipped=skipped)

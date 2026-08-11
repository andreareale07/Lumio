"""Backfill dei movimenti di investimento per le transazioni GIA'
importate prima che il parsing automatico (M09c, `import_job.py`) esistesse
— o comunque per qualunque transazione 'investment' non ancora collegata a
un `InvestmentTransaction`. Stessa logica di derivazione di `import_job.py`,
applicata a posteriori.

Idempotente: una transazione con un `InvestmentTransaction` gia' collegato
viene saltata, quindi puo' essere eseguito piu' volte senza duplicare nulla
(es. dopo un nuovo import che ha aggiunto altre righe 'investment' non
ancora derivate).
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment_transaction import InvestmentTransaction
from app.models.transaction import Transaction
from app.services.asset_matching import get_or_create_asset_by_isin
from app.services.position_service import recompute_position
from app.services.trade_parsing import parse_trade_description


@dataclass
class BackfillResult:
    scanned: int
    created: int
    skipped_already_linked: int
    skipped_unrecognized: int


async def backfill_investment_transactions(db: AsyncSession, workspace_id: uuid.UUID) -> BackfillResult:
    already_linked_ids = set(
        (
            await db.execute(
                select(InvestmentTransaction.transaction_id).where(
                    InvestmentTransaction.workspace_id == workspace_id,
                    InvestmentTransaction.transaction_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    candidates = (
        (
            await db.execute(
                select(Transaction).where(
                    Transaction.workspace_id == workspace_id,
                    Transaction.transaction_type == "investment",
                )
            )
        )
        .scalars()
        .all()
    )

    created = 0
    skipped_already_linked = 0
    skipped_unrecognized = 0
    # (conto, asset) -> valuta: solo le coppie toccate da questo backfill,
    # per non ricalcolare posizioni non interessate.
    touched_assets: dict[tuple[uuid.UUID, uuid.UUID], str] = {}

    for transaction in candidates:
        if transaction.id in already_linked_ids:
            skipped_already_linked += 1
            continue
        trade = parse_trade_description(transaction.description_raw)
        if trade is None:
            skipped_unrecognized += 1
            continue

        asset = await get_or_create_asset_by_isin(
            db, workspace_id, trade.isin, trade.asset_name, transaction.currency
        )
        price = abs(transaction.amount) / trade.quantity
        db.add(
            InvestmentTransaction(
                workspace_id=workspace_id,
                financial_account_id=transaction.financial_account_id,
                asset_id=asset.id,
                transaction_id=transaction.id,
                trade_date=transaction.transaction_date,
                type=trade.type,
                quantity=trade.quantity,
                price=price,
                amount=transaction.amount,
                currency=transaction.currency,
                source_type_raw=trade.source_type_raw,
            )
        )
        created += 1
        touched_assets[(transaction.financial_account_id, asset.id)] = transaction.currency

    for (account_id, asset_id), currency in touched_assets.items():
        await recompute_position(db, workspace_id, account_id, asset_id, currency)

    return BackfillResult(
        scanned=len(candidates),
        created=created,
        skipped_already_linked=skipped_already_linked,
        skipped_unrecognized=skipped_unrecognized,
    )

"""Persistenza di una `ParsedRow` come `Transaction` (+ eventuali
`Classification` e `InvestmentTransaction` collegate).

Estratto da `app/worker/jobs/import_job.py` per essere riusabile SIA dal job
batch di import SIA dalla risoluzione di una singola voce di REVIEW
ambigua (`POST /imports/{id}/review-items/{item_id}/decision`) — le due
strade devono produrre ESATTAMENTE gli stessi side-effect (piano approvato,
verifica esplicita §6): una riga risolta da REVIEW che e' anche un trade
Trade Republic deve generare la sua `InvestmentTransaction` collegata
esattamente come una riga NEW "normale", non una versione "light" che la
salta.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification import Classification
from app.models.investment_transaction import InvestmentTransaction
from app.models.transaction import Transaction
from app.services.asset_matching import get_or_create_asset_by_isin
from app.services.classification_pipeline import (
    ClassifiableRow,
    DeterministicOutcome,
    PipelineContext,
    classify_deterministic,
)
from app.services.confidence import needs_review as score_needs_review
from app.services.csv_import import ParsedRow
from app.services.merchant_extraction import extract_merchant
from app.services.position_service import recompute_position
from app.services.trade_parsing import ParsedTrade, parse_trade_description
from app.services.transaction_dedup import compute_dedup_fingerprint


@dataclass
class PreparedTransaction:
    transaction: Transaction
    outcome: DeterministicOutcome | None
    trade: ParsedTrade | None


def prepare_transaction_row(
    pipeline_ctx: PipelineContext,
    *,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    import_id: uuid.UUID | None,
    row: ParsedRow,
    needs_review_threshold: float,
) -> PreparedTransaction:
    """Costruisce la `Transaction` per una riga NEW (o risolta come tale) —
    stessa logica per-riga di `import_job._insert_transactions_and_complete`
    (merchant, classificazione deterministica, fingerprint), senza ancora
    toccare la sessione DB."""
    row.merchant = row.counterparty_name or extract_merchant(row.description_raw)

    classifiable_row = ClassifiableRow(
        description_raw=row.description_raw,
        description_normalized=row.description_normalized,
        merchant=row.merchant,
        transaction_type=row.transaction_type,
    )
    outcome = classify_deterministic(pipeline_ctx, classifiable_row)
    matched_category_id = outcome.category_id if outcome is not None else None

    fingerprint = compute_dedup_fingerprint(
        workspace_id=workspace_id,
        financial_account_id=financial_account_id,
        transaction_date=row.transaction_date,
        amount=row.amount,
        currency=row.currency,
        description_normalized=row.description_normalized,
        description_raw=row.description_raw,
        transaction_type=row.transaction_type,
    )

    transaction = Transaction(
        workspace_id=workspace_id,
        financial_account_id=financial_account_id,
        import_id=import_id,
        transaction_date=row.transaction_date,
        value_date=row.value_date,
        description_raw=row.description_raw,
        description_normalized=row.description_normalized,
        merchant=row.merchant,
        counterparty_name=row.counterparty_name,
        counterparty_iban=row.counterparty_iban,
        reference=row.reference,
        amount=row.amount,
        currency=row.currency,
        direction=row.direction,
        transaction_type=row.transaction_type,
        source_type_raw=row.source_type_raw,
        balance_after=row.balance_after,
        category_id=matched_category_id,
        dedup_fingerprint=fingerprint,
    )
    if outcome is not None:
        transaction.needs_review = score_needs_review(outcome.score, needs_review_threshold)

    trade = parse_trade_description(row.description_raw)
    return PreparedTransaction(transaction=transaction, outcome=outcome, trade=trade)


async def finalize_prepared_transactions(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    prepared: list[PreparedTransaction],
) -> None:
    """Aggiunge le `Transaction` preparate alla sessione e crea
    `Classification`/`InvestmentTransaction` collegate — un solo flush per
    l'intero batch passato (mai uno per riga: su un import di migliaia di
    movimenti costerebbe una query aggiuntiva per riga)."""
    if not prepared:
        return

    for prepared_row in prepared:
        db.add(prepared_row.transaction)

    # Sempre un flush (mai condizionato a "solo se c'e' una classificazione o
    # un trade"): il chiamante potrebbe aver bisogno degli id delle
    # Transaction appena create anche per altri motivi — es. collegare una
    # TransactionReviewItem risolta automaticamente da una decisione
    # pregressa (import_job.py) — non solo per Classification/
    # InvestmentTransaction.
    await db.flush()

    for prepared_row in prepared:
        if prepared_row.outcome is not None:
            db.add(
                Classification(
                    transaction_id=prepared_row.transaction.id,
                    method=prepared_row.outcome.method,
                    category_id=prepared_row.outcome.category_id,
                    score=prepared_row.outcome.score,
                    explanation=prepared_row.outcome.explanation,
                )
            )

    touched_assets: dict[uuid.UUID, str] = {}
    for prepared_row in prepared:
        trade = prepared_row.trade
        if trade is None:
            continue
        transaction = prepared_row.transaction
        asset = await get_or_create_asset_by_isin(
            db, workspace_id, trade.isin, trade.asset_name, transaction.currency
        )
        price = abs(transaction.amount) / trade.quantity
        db.add(
            InvestmentTransaction(
                workspace_id=workspace_id,
                financial_account_id=financial_account_id,
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
        touched_assets[asset.id] = transaction.currency

    for asset_id, currency in touched_assets.items():
        await recompute_position(db, workspace_id, financial_account_id, asset_id, currency)

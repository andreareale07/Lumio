"""Lato DB-aware di anteprima e suggerimenti delle regole: legge i movimenti
del workspace e li passa ai calcoli puri (`rule_preview_calc`,
`rule_suggestion_calc`). Nessuna scrittura.
"""
import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification import Classification
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.services.classification_loader import _MANUAL_CLASSIFICATION_METHODS
from app.services.rule_preview_calc import PreviewTx
from app.services.rules_engine import Probe, conditions_from_json, rule_matches

# Tetto di movimenti valutati per richiesta: la regex dell'utente gira in
# Python dentro la richiesta, quindi il lavoro va limitato. Si leggono i piu'
# recenti; l'anteprima dichiara `truncated` se ne esistono altri.
MAX_PREVIEW_ROWS = 50_000
MAX_SUGGESTION_POOL = 20_000


def _row_to_preview_tx(row, protected: bool) -> PreviewTx:
    return PreviewTx(
        id=row.id,
        transaction_date=row.transaction_date,
        amount=row.amount,
        description_raw=row.description_raw,
        description_normalized=row.description_normalized,
        merchant=row.merchant,
        category_id=row.category_id,
        protected=protected,
        currency=row.currency,
    )


async def load_preview_transactions(
    db: AsyncSession, workspace_id: uuid.UUID, limit: int = MAX_PREVIEW_ROWS
) -> tuple[list[PreviewTx], bool]:
    """Ritorna `(movimenti, troncato)`. `protected` = esiste una correzione
    manuale (`user`/`manual`) nello storico della classificazione."""
    manual = exists().where(
        Classification.transaction_id == Transaction.id,
        Classification.method.in_(_MANUAL_CLASSIFICATION_METHODS),
    )
    result = await db.execute(
        select(
            Transaction.id,
            Transaction.transaction_date,
            Transaction.amount,
            Transaction.description_raw,
            Transaction.description_normalized,
            Transaction.merchant,
            Transaction.category_id,
            Transaction.currency,
            manual.label("protected"),
        )
        .where(Transaction.workspace_id == workspace_id)
        .order_by(Transaction.transaction_date.desc(), Transaction.id)
        .limit(limit + 1)
    )
    rows = result.all()
    truncated = len(rows) > limit
    return [_row_to_preview_tx(row, bool(row.protected)) for row in rows[:limit]], truncated


async def load_corrected_transactions(db: AsyncSession, workspace_id: uuid.UUID) -> list[PreviewTx]:
    """Movimenti la cui categoria attuale l'ha scelta l'utente (storico
    append-only: esiste una classificazione `user` con la stessa categoria)."""
    chosen_by_user = exists().where(
        Classification.transaction_id == Transaction.id,
        Classification.method == "user",
        Classification.category_id == Transaction.category_id,
    )
    result = await db.execute(
        select(
            Transaction.id,
            Transaction.transaction_date,
            Transaction.amount,
            Transaction.description_raw,
            Transaction.description_normalized,
            Transaction.merchant,
            Transaction.category_id,
            Transaction.currency,
        ).where(Transaction.workspace_id == workspace_id, Transaction.category_id.is_not(None), chosen_by_user)
    )
    return [_row_to_preview_tx(row, True) for row in result.all()]


async def load_rule_matching_ids(db: AsyncSession, workspace_id: uuid.UUID, rule_id: uuid.UUID) -> set[uuid.UUID]:
    """Id dei movimenti del workspace che combaciano con le condizioni di una
    regola salvata. Senza tetto di righe: gira nel worker, non in una richiesta."""
    rule = await db.get(Rule, rule_id)
    if rule is None or rule.workspace_id != workspace_id:
        return set()
    conditions = conditions_from_json(rule.conditions)
    transactions, _ = await load_preview_transactions(db, workspace_id, limit=10_000_000)
    return {
        tx.id
        for tx in transactions
        if rule_matches(
            conditions,
            rule.match_mode,
            Probe(
                description_raw=tx.description_raw,
                description_normalized=tx.description_normalized,
                merchant=tx.merchant,
                amount=tx.amount,
            ),
        )
    }

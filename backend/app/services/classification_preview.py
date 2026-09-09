"""Anteprima sincrona della riclassificazione — SOLO livelli deterministici
(regole utente + sistema), NESSUNA scrittura, NESSUNA chiamata AI. E' quel
che rende l'operazione non spaventosa per l'utente: "312 cambierebbero
categoria, 87 correzioni manuali non verranno toccate" prima di premere
qualunque bottone, a costo di millisecondi invece che del tempo di un job
completo.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.transaction import Transaction
from app.services.classification_loader import load_eligible_transaction_ids, load_pipeline_context
from app.services.classification_pipeline import ClassifiableRow, classify_deterministic

_MAX_EXAMPLES_PER_CATEGORY = 5


@dataclass(frozen=True)
class CategoryPreviewBreakdown:
    category_id: uuid.UUID
    category_code: str
    category_name: str
    count: int
    examples: list[str]


@dataclass(frozen=True)
class ReclassificationPreview:
    scope: str
    total_candidates: int
    would_change: int
    breakdown: list[CategoryPreviewBreakdown]


async def preview_reclassification(
    db: AsyncSession, workspace_id: uuid.UUID, scope: str
) -> ReclassificationPreview:
    transaction_ids = await load_eligible_transaction_ids(db, workspace_id, scope)

    pipeline_ctx = await load_pipeline_context(db, workspace_id)

    per_category: dict[uuid.UUID, list[str]] = {}
    for txn_id in transaction_ids:
        txn = await db.get(Transaction, txn_id)
        if txn is None:
            continue
        row = ClassifiableRow(
            description_raw=txn.description_raw,
            description_normalized=txn.description_normalized,
            merchant=txn.merchant,
            transaction_type=txn.transaction_type,
        )
        outcome = classify_deterministic(pipeline_ctx, row)
        if outcome is None:
            continue
        # Contare solo un cambiamento REALE: se la pipeline propone la
        # STESSA categoria gia' assegnata, non e' un "would change" — evita
        # di allarmare l'utente con un numero che include righe gia' corrette.
        if outcome.category_id == txn.category_id:
            continue
        per_category.setdefault(outcome.category_id, []).append(txn.description_raw)

    breakdown = []
    if per_category:
        category_rows = (
            await db.execute(select(Category).where(Category.id.in_(per_category.keys())))
        ).scalars().all()
        category_by_id = {c.id: c for c in category_rows}
        for category_id, descriptions in per_category.items():
            category = category_by_id.get(category_id)
            if category is None:
                continue
            breakdown.append(
                CategoryPreviewBreakdown(
                    category_id=category_id,
                    category_code=category.code,
                    category_name=category.name,
                    count=len(descriptions),
                    examples=descriptions[:_MAX_EXAMPLES_PER_CATEGORY],
                )
            )
        breakdown.sort(key=lambda b: b.count, reverse=True)

    would_change = sum(b.count for b in breakdown)
    return ReclassificationPreview(
        scope=scope,
        total_candidates=len(transaction_ids),
        would_change=would_change,
        breakdown=breakdown,
    )

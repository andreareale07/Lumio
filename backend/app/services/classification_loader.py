"""Ponte DB-aware tra il motore puro della pipeline di classificazione
(`app/services/classification_pipeline.py`) e il DB — stessa separazione gia'
in uso per le regole (`rule_loader.py` / `rules_engine.py`). Qui vive solo
cio' che richiede una sessione DB (regole attive del workspace, mappa
code -> category_id); la logica di classificazione vera e propria resta
tutta pura, testabile senza DB.
"""
import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.classification import Classification
from app.models.transaction import Transaction
from app.services.classification_pipeline import PipelineContext
from app.services.rule_loader import load_active_rule_specs

_MANUAL_CLASSIFICATION_METHODS = ("user", "manual")


async def load_pipeline_context(
    db: AsyncSession, workspace_id: uuid.UUID, *, disabled_pattern_keys: frozenset[str] = frozenset()
) -> PipelineContext:
    """`disabled_pattern_keys`: sempre vuoto finche' non esiste una UI per
    disattivare un singolo pattern di sistema (piano di migrazione, step
    opzionale) — l'override via regola utente normale copre gia' il caso
    reale al 100%. Il parametro esiste da subito perche' aggiungere quella
    UI in futuro deve toccare solo questo loader, mai il motore ne' i tre
    chiamanti (import job, AI job, job di riclassificazione).
    """
    rules = await load_active_rule_specs(db, workspace_id)

    result = await db.execute(
        select(Category.code, Category.id).where(
            or_(Category.workspace_id.is_(None), Category.workspace_id == workspace_id),
            Category.is_active.is_(True),
        )
    )
    category_id_by_code = {code: cat_id for code, cat_id in result.all()}

    return PipelineContext(
        rules=rules,
        category_id_by_code=category_id_by_code,
        disabled_pattern_keys=disabled_pattern_keys,
    )


async def load_eligible_transaction_ids(
    db: AsyncSession, workspace_id: uuid.UUID, scope: str
) -> list[uuid.UUID]:
    """Transazioni eleggibili per la riclassificazione (job e preview
    condividono ESATTAMENTE questa query, non due copie che potrebbero
    divergere): mai una transazione con una `Classification(method IN
    ('user', 'manual'))` — invariante non negoziabile, verificata con
    `NOT EXISTS` sullo storico append-only, non su un confronto di valori.
    `scope='uncategorized'` restringe ulteriormente a `category_id IS NULL`;
    `scope='all_except_manual'` non aggiunge altro filtro."""
    manual_classification_exists = exists().where(
        Classification.transaction_id == Transaction.id,
        Classification.method.in_(_MANUAL_CLASSIFICATION_METHODS),
    )
    query = select(Transaction.id).where(
        Transaction.workspace_id == workspace_id, ~manual_classification_exists
    )
    if scope == "uncategorized":
        query = query.where(Transaction.category_id.is_(None))
    result = await db.execute(query.order_by(Transaction.transaction_date))
    return [row[0] for row in result.all()]

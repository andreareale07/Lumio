"""Decide se un import deve accodare la classificazione AI disaccoppiata
(`ai_classification_job.py`) — estratto da `import_job.py` per essere
richiamabile anche da `POST /imports/{id}/review-items/{item_id}/decision`,
quando l'ultima voce di REVIEW risolta fa transitare l'import da
'ready_for_review' a 'completed' (piano approvato: l'enqueue AI avviene
SOLO quando l'import e' davvero completo, mai mentre restano decisioni
obbligatorie pendenti).

Ricalcola sempre dallo stato REALE delle transazioni dell'import al momento
della chiamata (query, non un contatore in-memory portato da un punto
diverso della pipeline) — funziona identicamente sia quando tutte le
transazioni sono state inserite in un colpo dal job, sia quando alcune sono
arrivate piu' tardi dalla risoluzione di una REVIEW.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_ import Import
from app.models.transaction import Transaction
from app.services.ai_profile_service import get_active_profile
from app.services.system_classification import is_ai_eligible


async def prepare_ai_classification_trigger(
    db: AsyncSession, workspace_id: uuid.UUID, import_row: Import
) -> bool:
    """Da chiamare DENTRO la stessa transazione DB che porta l'import a
    'completed', subito prima del commit: imposta
    `ai_classification_status`/`ai_transactions_total` sull'import. Ritorna
    True se il chiamante deve accodare `enqueue_classify_import_job` DOPO il
    commit (mai prima: il job worker leggerebbe uno stato non ancora
    visibile ad altre connessioni)."""
    active_ai_profile = await get_active_profile(db, workspace_id)
    if active_ai_profile is None:
        import_row.ai_classification_status = "skipped"
        import_row.ai_transactions_total = 0
        return False

    result = await db.execute(
        select(Transaction.transaction_type).where(
            Transaction.workspace_id == workspace_id,
            Transaction.import_id == import_row.id,
            Transaction.category_id.is_(None),
        )
    )
    eligible_count = sum(1 for (transaction_type,) in result.all() if is_ai_eligible(transaction_type))

    if eligible_count > 0:
        import_row.ai_classification_status = "pending"
        import_row.ai_transactions_total = eligible_count
        return True

    import_row.ai_classification_status = "skipped"
    import_row.ai_transactions_total = 0
    return False

"""Ponte DB-aware tra il worker import e `AIClassifier` (SPEC §25, §28:
Rules -> AI, invocato solo quando nessuna regola ha classificato la riga).
Stessa separazione di `rule_loader.py`/`rules_engine.py`: qui vive solo cio'
che richiede il DB (elenco categorie del workspace), la chiamata al provider
resta nell'istanza `AIClassifier' gia' costruita dal chiamante.
"""
import logging
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import (
    AIClassificationResult,
    AIClassifier,
    AIProviderError,
    CategoryOption,
    ClassifiableTransaction,
)
from app.models.category import Category

logger = logging.getLogger("lumio.ai")


async def load_category_options(db: AsyncSession, workspace_id: uuid.UUID) -> list[CategoryOption]:
    result = await db.execute(
        select(Category).where(
            or_(Category.workspace_id.is_(None), Category.workspace_id == workspace_id),
            Category.is_active.is_(True),
        )
    )
    return [CategoryOption(id=c.id, code=c.code, name=c.name) for c in result.scalars().all()]


async def classify_transaction(
    classifier: AIClassifier, categories: list[CategoryOption], transaction: ClassifiableTransaction
) -> AIClassificationResult | None:
    """Non solleva mai: un provider irraggiungibile o una risposta non
    interpretabile equivalgono a "nessuna classificazione AI" per questa
    riga, non a un fallimento dell'intero import (SPEC §25, l'AI resta
    sempre opzionale)."""
    if not categories:
        return None
    try:
        return await classifier.classify(transaction, categories)
    except AIProviderError:
        logger.warning("classificazione AI fallita (provider=%s)", classifier.provider, exc_info=True)
        return None

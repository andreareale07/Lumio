"""Ponte DB-aware tra il worker import e `AIClassifier` (SPEC §25, §28:
Rules -> AI, invocato solo quando nessuna regola ha classificato la riga).
Stessa separazione di `rule_loader.py`/`rules_engine.py`: qui vive solo cio'
che richiede il DB (elenco categorie del workspace), la chiamata al provider
resta nell'istanza `AIClassifier' gia' costruita dal chiamante.
"""
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import (
    AIClassificationResult,
    AIClassifier,
    AIProviderError,
    CategoryOption,
    ClassifiableTransaction,
)
from app.classification.taxonomy import TAXONOMY_BY_CODE
from app.models.category import Category

logger = logging.getLogger("lumio.ai")


def kinds_for_transaction(direction: str, transaction_type: str) -> frozenset[str]:
    """Quali `kind` di categoria offrire all'AI per questa transazione —
    dimezza le opzioni (e con esse le occasioni di sbagliare) offrendo solo
    cio' che e' semanticamente coerente col segno/tipo del movimento, invece
    della tassonomia intera per ogni riga. `neutral` e' sempre incluso
    (i contenitori "bonifico non specificato"/"da classificare" sono un
    fallback legittimo in ogni caso).

    `refund` e' un caso speciale: un rimborso e' la NEGAZIONE di una spesa
    (es. reso Amazon), non un'entrata — offrire solo `income` nasconderebbe
    la spesa originale dalle analytics. `adjustment` e' troppo generico per
    restringere: resta aperto su entrambi i lati.
    """
    if transaction_type == "refund":
        return frozenset({"expense", "neutral"})
    if transaction_type == "adjustment":
        return frozenset({"expense", "income", "neutral"})
    primary = "expense" if direction == "debit" else "income"
    return frozenset({primary, "neutral"})


@dataclass(frozen=True)
class ClassificationAttempt:
    """Distingue "il modello non ha trovato un match sensato" (`result is
    None`, `provider_error=False` — esito legittimo, mai un fallimento) da
    "il provider non ha risposto affatto" (`provider_error=True`). Bug reale
    osservato dall'utente su un provider Ollama locale spento a meta' import:
    prima, entrambi i casi collassavano sullo stesso `None`, e il chiamante
    (`ai_classification_job.py`) incrementava comunque il contatore "x/N
    classificati" per OGNI riga tentata — durante un'interruzione totale del
    provider, il job sembrava progredire normalmente mentre in realta' ogni
    singola chiamata falliva silenziosamente."""

    result: AIClassificationResult | None
    provider_error: bool


async def load_category_options(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    kinds: frozenset[str] | None = None,
    leaves_only: bool = True,
) -> list[CategoryOption]:
    """`kinds=None` carica tutto (usato oggi solo dai chiamanti che non
    filtrano ancora, es. suggerimenti regole); il job AI passa sempre
    `kinds_for_transaction(...)`. `leaves_only=True` esclude le radici che
    hanno figli: farsi assegnare un padre invece di una foglia specifica non
    aiuta ne' l'utente ne' `by_category` (che riaccorpa comunque sul padre),
    e dimezza ulteriormente le opzioni offerte al modello.
    """
    result = await db.execute(
        select(Category).where(
            or_(Category.workspace_id.is_(None), Category.workspace_id == workspace_id),
            Category.is_active.is_(True),
        )
    )
    categories = result.scalars().all()
    by_id = {c.id: c for c in categories}
    parent_ids_with_children = {c.parent_id for c in categories if c.parent_id is not None}

    options = []
    for c in categories:
        if kinds is not None and c.kind not in kinds:
            continue
        if leaves_only and c.parent_id is None and c.id in parent_ids_with_children:
            continue
        parent = by_id.get(c.parent_id) if c.parent_id is not None else None
        taxonomy_entry = TAXONOMY_BY_CODE.get(c.code)
        options.append(
            CategoryOption(
                id=c.id,
                code=c.code,
                name=c.name,
                parent_code=parent.code if parent is not None else None,
                parent_name=parent.name if parent is not None else None,
                kind=c.kind,
                hint=taxonomy_entry.hint if taxonomy_entry is not None else None,
            )
        )
    return options


async def classify_transaction(
    classifier: AIClassifier, categories: list[CategoryOption], transaction: ClassifiableTransaction
) -> ClassificationAttempt:
    """Non solleva mai: un provider irraggiungibile o una risposta non
    interpretabile equivalgono a "nessuna classificazione AI" per questa
    riga, non a un fallimento dell'intero import (SPEC §25, l'AI resta
    sempre opzionale) — ma il chiamante puo' distinguere le due cause
    tramite `ClassificationAttempt.provider_error` per decidere se
    interrompere il job (troppi fallimenti di provider consecutivi) invece
    di continuare a "tentare" righe che falliranno comunque."""
    if not categories:
        return ClassificationAttempt(result=None, provider_error=False)
    try:
        result = await classifier.classify(transaction, categories)
        return ClassificationAttempt(result=result, provider_error=False)
    except AIProviderError:
        logger.warning("classificazione AI fallita (provider=%s)", classifier.provider, exc_info=True)
        return ClassificationAttempt(result=None, provider_error=True)

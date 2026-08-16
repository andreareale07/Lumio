"""Pipeline di classificazione — un solo punto che conosce l'intero ordine,
usato da import job, AI job e (rework successivo) job di riclassificazione.
Prima di questo modulo "regole -> AI" non era un oggetto nel codice: era un
ordine emergente scritto in due punti scollegati (`import_job.py` per le
regole, `ai_classification_job.py` per l'AI, la cui query si limitava a
"tutto cio' che e' ancora NULL merita l'AI", senza altra condizione). Non
c'era un posto dove inserire un livello intermedio ne' dove rieseguire la
stessa logica fuori dall'import.

Ordine (i livelli 4/5 arrivano nei passi successivi del rework, questo
modulo e' gia' pensato per accoglierli senza cambiare la firma pubblica):

    1. regole utente        (rules_engine.evaluate — l'utente vince sempre)
    2. sistema: tipo         (system_classification.classify_by_transaction_type)
    3. sistema: pattern      (system_classification.classify_by_pattern)
    4. AI                    (solo su cio' che resta, filtrata per kind)
    5. confidence/needs_review

Puro: nessuna dipendenza da DB. Il ponte DB-aware che costruisce
`PipelineContext` vive in `app/services/classification_loader.py`.
"""
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.services.rules_engine import Probe, RuleSpec, evaluate
from app.services.system_classification import (
    classify_by_pattern,
    classify_by_transaction_type,
    is_ai_eligible,
)

__all__ = [
    "ClassifiableRow",
    "PipelineContext",
    "DeterministicOutcome",
    "classify_deterministic",
    "is_ai_eligible",
]


@dataclass(frozen=True)
class ClassifiableRow:
    description_raw: str
    description_normalized: str | None
    merchant: str | None
    transaction_type: str


@dataclass(frozen=True)
class PipelineContext:
    rules: list[RuleSpec]
    category_id_by_code: dict[str, uuid.UUID]
    # Sempre vuoto finche' non esiste una UI per disattivare un singolo
    # pattern di sistema — vedi app/services/classification_loader.py.
    disabled_pattern_keys: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class DeterministicOutcome:
    category_id: uuid.UUID
    method: str  # "rule" | "system"
    score: Decimal
    explanation: str | None


def classify_deterministic(ctx: PipelineContext, row: ClassifiableRow) -> DeterministicOutcome | None:
    """Ritorna la classificazione deterministica di una riga, o `None` se
    nessun livello deterministico ha trovato nulla (la riga prosegue verso
    l'AI, se `is_ai_eligible(row.transaction_type)` lo permette).

    Non solleva mai, non forza mai una categoria diversa da quella dedotta:
    se il livello 2 propone un `code` che non esiste piu' nella tassonomia
    del workspace (categoria disattivata dall'utente), la riga resta senza
    classificazione a questo livello — mai un fallback silenzioso su
    un'altra categoria.
    """
    probe = Probe(
        description_raw=row.description_raw,
        description_normalized=row.description_normalized,
        merchant=row.merchant,
    )
    rule_category_id = evaluate(ctx.rules, probe)
    if rule_category_id is not None:
        return DeterministicOutcome(
            category_id=rule_category_id, method="rule", score=Decimal("1.00"), explanation=None
        )

    system_code = classify_by_transaction_type(row.transaction_type, row.description_raw)
    if system_code is not None:
        category_id = ctx.category_id_by_code.get(system_code)
        if category_id is not None:
            return DeterministicOutcome(
                category_id=category_id,
                method="system",
                score=Decimal("1.00"),
                explanation=f"tipo movimento: {row.transaction_type}",
            )

    pattern_match = classify_by_pattern(row, disabled_keys=ctx.disabled_pattern_keys)
    if pattern_match is not None:
        category_id = ctx.category_id_by_code.get(pattern_match.category_code)
        if category_id is not None:
            return DeterministicOutcome(
                category_id=category_id,
                method="system",
                score=Decimal("0.95"),
                explanation=f"catalogo di sistema: {pattern_match.pattern_key}",
            )

    return None

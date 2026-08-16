"""Motore di valutazione delle regole (SPEC §23), puro — nessuna dipendenza
da DB/FastAPI, unit-testabile in isolamento come `csv_import.py`. Il
caricamento delle regole attive dal DB (ordinate, filtrate per workspace) e
la creazione delle `Classification` restano a carico del chiamante
DB-aware (`app/api/v1/transactions.py`, `app/worker/jobs/import_job.py`).

Ordine di valutazione (scelta minore, documentata nel piano di M06):
`priority` crescente, poi `created_at` crescente — prima regola attiva che
matcha vince, nessuna combinazione di piu' regole.
"""
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class MatchableRow(Protocol):
    description_raw: str
    description_normalized: str | None
    merchant: str | None


@dataclass(frozen=True)
class Probe:
    """Implementazione concreta di `MatchableRow` per chi non ha gia' un
    oggetto adatto sottomano (es. `ParsedRow` non ha `merchant`, i payload
    di creazione manuale non hanno `description_normalized`).
    """

    description_raw: str
    description_normalized: str | None
    merchant: str | None


@dataclass(frozen=True)
class RuleSpec:
    id: uuid.UUID
    field: str
    operator: str
    value: str
    category_id: uuid.UUID
    priority: int
    created_at: datetime


def sort_rules(rules: list[RuleSpec]) -> list[RuleSpec]:
    return sorted(rules, key=lambda r: (r.priority, r.created_at))


def _field_value(row: MatchableRow, field: str) -> str | None:
    if field == "merchant":
        return row.merchant
    return row.description_normalized or row.description_raw


def matches(field: str, operator: str, value: str, row: MatchableRow) -> bool:
    """Primitiva di matching pubblica, riusata sia dalle regole utente
    (`evaluate` sotto) sia dal catalogo di pattern di sistema
    (`app/classification/catalog.py` + `app/services/system_classification.py`,
    livello 3 della pipeline di classificazione): due implementazioni
    separate della stessa logica (case-insensitive, stessi 6 operatori)
    divergerebbero silenziosamente nel tempo.
    """
    if operator == "merchant_equals":
        target = row.merchant
        if target is None:
            return False
        return target.strip().lower() == value.strip().lower()

    target = _field_value(row, field)
    if target is None:
        return False

    if operator == "regex":
        return re.search(value, target, re.IGNORECASE) is not None

    target_lower = target.lower()
    value_lower = value.lower()
    if operator == "equals":
        return target_lower.strip() == value_lower.strip()
    if operator == "contains":
        return value_lower in target_lower
    if operator == "starts_with":
        return target_lower.startswith(value_lower)
    if operator == "ends_with":
        return target_lower.endswith(value_lower)
    return False


def evaluate(rules: list[RuleSpec], row: MatchableRow) -> uuid.UUID | None:
    """Ritorna il `category_id` della prima regola (gia' ordinata per
    priorita') che matcha, o None se nessuna regola matcha. Il chiamante
    passa solo regole gia' filtrate per `is_active=True` e per workspace.
    """
    for rule in sort_rules(rules):
        if matches(rule.field, rule.operator, rule.value, row):
            return rule.category_id
    return None

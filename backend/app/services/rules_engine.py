"""Motore di valutazione delle regole (SPEC §23), puro — nessuna dipendenza
da DB/FastAPI, unit-testabile in isolamento come `csv_import.py`. Il
caricamento delle regole attive dal DB (ordinate, filtrate per workspace) e
la creazione delle `Classification` restano a carico del chiamante
DB-aware (`app/api/v1/transactions.py`, `app/worker/jobs/import_job.py`).

Ordine di valutazione (scelta minore, documentata nel piano di M06):
`priority` crescente, poi `created_at` crescente — prima regola attiva che
matcha vince, nessuna combinazione di piu' regole.

Una regola ha una o piu' condizioni (`Condition`) combinate con `match_mode`:
`all` (tutte vere, E) oppure `any` (almeno una, O). Le condizioni sono di
testo (`description`/`merchant` + operatore) o sull'importo (`amount` +
`between`, sul valore assoluto: una rata e' -487,30 ma l'utente ragiona 487,30).
"""
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

AMOUNT_FIELD = "amount"
AMOUNT_OPERATOR = "between"
MATCH_MODES = ("all", "any")

# Tetto alla lunghezza di una regex scritta dall'utente e controllo dei
# quantificatori annidati (`(a+)+`): `re` di Python non ha timeout e la
# regex gira sia nel worker sia nell'anteprima, dentro una richiesta.
MAX_REGEX_LENGTH = 200
_NESTED_QUANTIFIER = re.compile(r"\((?:[^()\\]|\\.)*[+*](?:[^()\\]|\\.)*\)\s*(?:[+*]|\{\d)")


class MatchableRow(Protocol):
    description_raw: str
    description_normalized: str | None
    merchant: str | None


@dataclass(frozen=True)
class Probe:
    """Implementazione concreta di `MatchableRow` per chi non ha gia' un
    oggetto adatto sottomano (es. `ParsedRow` non ha `merchant`, i payload
    di creazione manuale non hanno `description_normalized`). `amount` e'
    opzionale: senza, le condizioni sull'importo non scattano mai.
    """

    description_raw: str
    description_normalized: str | None
    merchant: str | None
    amount: Decimal | None = None


@dataclass(frozen=True)
class Condition:
    field: str  # "description" | "merchant" | "amount"
    operator: str
    value: str = ""
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


@dataclass(frozen=True)
class RuleSpec:
    id: uuid.UUID
    conditions: tuple[Condition, ...]
    category_id: uuid.UUID
    priority: int
    created_at: datetime
    match_mode: str = "all"


def check_regex_safety(pattern: str) -> None:
    """Solleva `ValueError` se la regex e' invalida, troppo lunga o ha
    quantificatori annidati (rischio di backtracking catastrofico)."""
    if len(pattern) > MAX_REGEX_LENGTH:
        raise ValueError(f"regex troppo lunga (massimo {MAX_REGEX_LENGTH} caratteri)")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regex pattern: {exc}") from exc
    if _NESTED_QUANTIFIER.search(pattern):
        raise ValueError("regex non ammessa: quantificatori annidati")


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def condition_from_dict(data: dict[str, Any]) -> Condition:
    """Costruisce una `Condition` dal JSON salvato in `rules.conditions`."""
    field = str(data.get("field", ""))
    if field == AMOUNT_FIELD:
        return Condition(
            field=AMOUNT_FIELD,
            operator=AMOUNT_OPERATOR,
            min_amount=_to_decimal(data.get("min")),
            max_amount=_to_decimal(data.get("max")),
        )
    return Condition(field=field, operator=str(data.get("operator", "")), value=str(data.get("value", "")))


def conditions_from_json(items: list[dict[str, Any]] | None) -> tuple[Condition, ...]:
    return tuple(condition_from_dict(item) for item in (items or []))


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


def condition_matches(condition: Condition, row: MatchableRow) -> bool:
    if condition.field == AMOUNT_FIELD:
        amount = getattr(row, "amount", None)
        if amount is None:
            return False
        magnitude = abs(Decimal(amount))
        if condition.min_amount is not None and magnitude < condition.min_amount:
            return False
        if condition.max_amount is not None and magnitude > condition.max_amount:
            return False
        return condition.min_amount is not None or condition.max_amount is not None
    return matches(condition.field, condition.operator, condition.value, row)


def rule_matches(conditions: tuple[Condition, ...], match_mode: str, row: MatchableRow) -> bool:
    """Una regola senza condizioni non scatta mai."""
    if not conditions:
        return False
    results = (condition_matches(condition, row) for condition in conditions)
    return any(results) if match_mode == "any" else all(results)


def evaluate(rules: list[RuleSpec], row: MatchableRow) -> uuid.UUID | None:
    """Ritorna il `category_id` della prima regola (gia' ordinata per
    priorita') che matcha, o None se nessuna regola matcha. Il chiamante
    passa solo regole gia' filtrate per `is_active=True` e per workspace.
    """
    for rule in sort_rules(rules):
        if rule_matches(rule.conditions, rule.match_mode, row):
            return rule.category_id
    return None

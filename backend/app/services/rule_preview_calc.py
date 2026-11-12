"""Anteprima dell'impatto di una regola NON salvata — funzioni pure, nessun
DB. Risponde a "quali movimenti toccherebbe questa regola?" con la stessa
semantica del motore (`rules_engine.rule_matches`), dividendo i movimenti che
combaciano in tre gruppi:

- `change`: la categoria cambierebbe (e il movimento non e' una correzione
  manuale);
- `ok`: e' gia' nella categoria bersaglio, nessun effetto;
- `protected`: ha una correzione manuale (`user`/`manual`) in un'altra
  categoria. Le correzioni manuali vincono sempre: la regola non la tocca.

Gli intervalli da evidenziare (`spans`) sono calcolati qui, con la stessa
logica dei confronti, cosi' il frontend non rifa' i match (la regex non e'
riproducibile fedelmente in JavaScript).
"""
import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.rules_engine import AMOUNT_FIELD, Condition, Probe, rule_matches

GROUPS = ("change", "ok", "protected")
_MAX_SPANS_PER_CONDITION = 5
_MAX_CONFLICT_SAMPLES = 5


@dataclass(frozen=True)
class PreviewTx:
    id: uuid.UUID
    transaction_date: date
    amount: Decimal
    description_raw: str
    description_normalized: str | None
    merchant: str | None
    category_id: uuid.UUID | None
    protected: bool
    currency: str = "EUR"

    @property
    def text(self) -> str:
        """Il testo che il campo `description` delle regole confronta."""
        return self.description_normalized or self.description_raw


@dataclass(frozen=True)
class PreviewMatch:
    tx: PreviewTx
    group: str
    spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PreviewResult:
    would_change: int
    already_correct: int
    protected: int
    # Dei `would_change`, quanti hanno gia' una categoria diversa (gli altri
    # sono senza categoria): solo questi sono una "ri-categorizzazione".
    recategorized: int
    # Movimenti che combaciano e hanno gia' un'ALTRA categoria, protetti o no:
    # il segnale che la frase e' condivisa con un'altra categoria.
    other_category: int
    conflict_samples: tuple[str, ...]  # descrizioni distinte, le piu' recenti
    matches: tuple[PreviewMatch, ...]  # solo la pagina richiesta


def _occurrences(haystack_lower: str, needle_lower: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    while needle_lower and len(spans) < _MAX_SPANS_PER_CONDITION:
        index = haystack_lower.find(needle_lower, start)
        if index < 0:
            break
        spans.append((index, index + len(needle_lower)))
        start = index + len(needle_lower)
    return spans


def condition_spans(condition: Condition, text: str) -> list[tuple[int, int]]:
    """Dove, nella descrizione, la condizione ha trovato corrispondenza.
    Le condizioni sul merchant o sull'importo non evidenziano nulla."""
    if condition.field != "description":
        return []
    lowered = text.lower()
    value = condition.value
    if condition.operator == "contains":
        return _occurrences(lowered, value.lower())
    if condition.operator == "starts_with":
        return [(0, len(value))] if lowered.startswith(value.lower()) else []
    if condition.operator == "ends_with":
        return [(len(text) - len(value), len(text))] if lowered.endswith(value.lower()) else []
    if condition.operator == "equals":
        return [(0, len(text))] if lowered.strip() == value.lower().strip() else []
    if condition.operator == "regex":
        found: list[tuple[int, int]] = []
        for match in re.finditer(value, text, re.IGNORECASE):
            if match.end() > match.start():
                found.append((match.start(), match.end()))
            if len(found) >= _MAX_SPANS_PER_CONDITION:
                break
        return found
    return []


def merge_spans(spans: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def match_spans(conditions: tuple[Condition, ...], text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for condition in conditions:
        if condition.field != AMOUNT_FIELD:
            spans.extend(condition_spans(condition, text))
    return merge_spans(spans)


def group_for(tx: PreviewTx, target_category_id: uuid.UUID) -> str:
    if tx.category_id == target_category_id:
        return "ok"
    if tx.protected:
        return "protected"
    return "change"


def build_preview(
    conditions: tuple[Condition, ...],
    match_mode: str,
    target_category_id: uuid.UUID,
    transactions: list[PreviewTx],
    *,
    group: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PreviewResult:
    counts = {"change": 0, "ok": 0, "protected": 0}
    recategorized = 0
    conflicts: list[PreviewTx] = []
    hits: list[tuple[PreviewTx, str]] = []
    for tx in transactions:
        probe = Probe(
            description_raw=tx.description_raw,
            description_normalized=tx.description_normalized,
            merchant=tx.merchant,
            amount=tx.amount,
        )
        if not rule_matches(conditions, match_mode, probe):
            continue
        tx_group = group_for(tx, target_category_id)
        counts[tx_group] += 1
        if tx_group == "change" and tx.category_id is not None:
            recategorized += 1
        if tx.category_id is not None and tx.category_id != target_category_id:
            conflicts.append(tx)
        if group is None or tx_group == group:
            hits.append((tx, tx_group))

    hits.sort(key=lambda item: (item[0].transaction_date, str(item[0].id)), reverse=True)
    page = hits[offset : offset + limit]
    matches = tuple(
        PreviewMatch(tx=tx, group=tx_group, spans=match_spans(conditions, tx.text)) for tx, tx_group in page
    )
    samples: list[str] = []
    for tx in sorted(conflicts, key=lambda item: (item.transaction_date, str(item.id)), reverse=True):
        if tx.text not in samples:
            samples.append(tx.text)
        if len(samples) >= _MAX_CONFLICT_SAMPLES:
            break
    return PreviewResult(
        would_change=counts["change"],
        already_correct=counts["ok"],
        protected=counts["protected"],
        recategorized=recategorized,
        other_category=len(conflicts),
        conflict_samples=tuple(samples),
        matches=matches,
    )

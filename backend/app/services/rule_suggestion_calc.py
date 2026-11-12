"""Suggerimenti di regola dalle correzioni manuali (SPEC §29) — funzioni pure,
nessun DB. Sostituisce il raggruppamento per testo identico: i movimenti di una
banca hanno quasi sempre una parte che cambia (riferimenti, numeri), quindi
due movimenti dello stesso tipo non hanno mai la descrizione uguale.

Idea: dei movimenti che l'utente ha spostato nella stessa categoria si cercano
le **frasi stabili** (sequenze di parole senza cifre) comuni alla maggior parte
di essi, e se ne misura l'effetto su TUTTI i movimenti del workspace con la
stessa classificazione dell'anteprima (cambiano / gia' giusti / protetti).
Per ogni suggerimento escono fino a tre opzioni:

- `recommended`: la frase che copre i movimenti corretti cambiando meno
  categorie altrui (a parita', 2+ parole e la piu' corta);
- `precise`: la consigliata piu' una seconda frase indipendente (restringe
  anche ai movimenti futuri);
- `broad`: una frase piu' ampia che copre comunque i movimenti corretti.

`ambiguous` segnala che la frase piu' ampia e' condivisa anche da un'altra
categoria scelta dall'utente: il testo da solo non basta a distinguerle.
Euristica deterministica, senza AI.
"""
import math
import uuid
from dataclasses import dataclass

from app.services.rule_preview_calc import PreviewTx, build_preview, group_for
from app.services.rules_engine import Condition, Probe, RuleSpec, evaluate

THRESHOLD = 2
MAX_GROUPS = 10
MAX_CANDIDATES = 40
MAX_NGRAM = 4
# Connettivi italiani: una frase non puo' iniziare o finire con uno di essi.
_STOPWORDS = frozenset(
    {"per", "di", "da", "il", "la", "lo", "le", "i", "gli", "un", "una", "in", "su", "con", "a", "e", "del", "della"}
)


@dataclass(frozen=True)
class OptionCalc:
    key: str  # "precise" | "recommended" | "broad"
    conditions: tuple[Condition, ...]
    match_mode: str
    would_change: int
    already_correct: int
    protected: int


@dataclass(frozen=True)
class SuggestionCalc:
    category_id: uuid.UUID
    transaction_ids: tuple[uuid.UUID, ...]
    label: str
    ambiguous: bool
    options: tuple[OptionCalc, ...]


def _has_letter(token: str) -> bool:
    return any(ch.isalpha() for ch in token)


def _is_stable(token: str) -> bool:
    return _has_letter(token) and not any(ch.isdigit() for ch in token)


def stable_runs(text: str) -> list[list[str]]:
    """Sequenze di parole stabili: un token con cifre (TRN, importi, date) o
    senza lettere (`-`, `/`) interrompe la sequenza."""
    runs: list[list[str]] = []
    current: list[str] = []
    for token in text.split():
        if _is_stable(token):
            current.append(token)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


@dataclass(frozen=True)
class _Phrase:
    lower: str
    display: str
    tokens: frozenset[str]
    n_tokens: int


def _phrase_ok(parts: list[str]) -> bool:
    if parts[0].lower().strip(".,;:") in _STOPWORDS or parts[-1].lower().strip(".,;:") in _STOPWORDS:
        return False
    if len(parts) == 1 and len(parts[0]) < 4:
        return False
    return True


def phrases_of(text: str) -> dict[str, _Phrase]:
    found: dict[str, _Phrase] = {}
    for run in stable_runs(text):
        for n in range(1, min(MAX_NGRAM, len(run)) + 1):
            for start in range(len(run) - n + 1):
                parts = run[start : start + n]
                if not _phrase_ok(parts):
                    continue
                display = " ".join(parts)
                lower = display.lower()
                found.setdefault(
                    lower,
                    _Phrase(lower, display, frozenset(p.lower() for p in parts), n),
                )
    return found


def _contains_condition(phrase: _Phrase) -> Condition:
    return Condition(field="description", operator="contains", value=phrase.display)


def _already_covered(rules: list[RuleSpec], tx: PreviewTx) -> bool:
    probe = Probe(
        description_raw=tx.description_raw,
        description_normalized=tx.description_normalized,
        merchant=tx.merchant,
        amount=tx.amount,
    )
    return evaluate(rules, probe) == tx.category_id


def _option(key: str, conditions: tuple[Condition, ...], category_id: uuid.UUID, pool: list[PreviewTx]) -> OptionCalc:
    result = build_preview(conditions, "all", category_id, pool, limit=1)
    return OptionCalc(
        key=key,
        conditions=conditions,
        match_mode="all",
        would_change=result.would_change,
        already_correct=result.already_correct,
        protected=result.protected,
    )


def _merchant_suggestions(
    corrected: list[PreviewTx], pool: list[PreviewTx]
) -> tuple[list[SuggestionCalc], set[uuid.UUID]]:
    groups: dict[tuple[uuid.UUID, str], list[PreviewTx]] = {}
    for tx in corrected:
        if tx.merchant and tx.merchant.strip() and tx.category_id is not None:
            groups.setdefault((tx.category_id, tx.merchant.strip().lower()), []).append(tx)
    suggestions: list[SuggestionCalc] = []
    used: set[uuid.UUID] = set()
    for (category_id, _), members in groups.items():
        if len(members) < THRESHOLD:
            continue
        merchant = (members[0].merchant or "").strip()
        condition = Condition(field="merchant", operator="merchant_equals", value=merchant)
        option = _option("recommended", (condition,), category_id, pool)
        # Un merchant condiviso con altre categorie non distingue nulla (es.
        # "Bonifico Sepa Istantaneo Trn" estratto da tutti i bonifici): se
        # toglierebbe da altre categorie piu' movimenti di quanti sono gia'
        # giusti, i movimenti passano all'analisi delle frasi.
        if option.would_change > option.already_correct:
            continue
        suggestions.append(
            SuggestionCalc(
                category_id=category_id,
                transaction_ids=tuple(t.id for t in members),
                label=merchant,
                ambiguous=False,
                options=(option,),
            )
        )
        used.update(t.id for t in members)
    return suggestions, used


def _text_suggestion(
    category_id: uuid.UUID, members: list[PreviewTx], pool: list[PreviewTx], pool_lower: list[tuple[PreviewTx, str]]
) -> tuple[SuggestionCalc, _Phrase] | None:
    need = max(THRESHOLD, math.ceil(len(members) / 2))
    document_frequency: dict[str, int] = {}
    catalog: dict[str, _Phrase] = {}
    for tx in members:
        for lower, phrase in phrases_of(tx.text).items():
            document_frequency[lower] = document_frequency.get(lower, 0) + 1
            catalog.setdefault(lower, phrase)
    ranked = sorted(
        (lower for lower, df in document_frequency.items() if df >= need),
        key=lambda lower: (-document_frequency[lower], -catalog[lower].n_tokens, -len(lower), lower),
    )[:MAX_CANDIDATES]
    if not ranked:
        return None

    stats: dict[str, tuple[int, int]] = {}  # lower -> (cambiano, totale nel workspace)
    for lower in ranked:
        change = total = 0
        for tx, text in pool_lower:
            if lower in text:
                total += 1
                if group_for(tx, category_id) == "change":
                    change += 1
        stats[lower] = (change, total)

    def recommended_key(lower: str) -> tuple:
        phrase = catalog[lower]
        return (-document_frequency[lower], stats[lower][0], 0 if phrase.n_tokens >= 2 else 1, len(phrase.display))

    best = min(ranked, key=recommended_key)
    recommended = catalog[best]
    options: list[OptionCalc] = []

    # precisa: una seconda frase indipendente (nessuna parola in comune).
    best_coverage = document_frequency[best]
    narrowing: list[tuple[tuple, _Phrase]] = []
    for lower in ranked:
        phrase = catalog[lower]
        if phrase.n_tokens < 2 or document_frequency[lower] < best_coverage or phrase.tokens & recommended.tokens:
            continue
        both = sum(1 for _, text in pool_lower if best in text and lower in text)
        narrowing.append(((both, stats[lower][1], -phrase.n_tokens, len(phrase.display)), phrase))
    precise = min(narrowing, key=lambda item: item[0])[1] if narrowing else None

    # ampia: copre comunque i movimenti corretti ma piu' movimenti del workspace.
    eligible = [
        catalog[lower]
        for lower in ranked
        if catalog[lower].n_tokens >= 2 and document_frequency[lower] >= best_coverage
    ]
    widest = max(eligible, key=lambda p: (stats[p.lower][1], len(p.display)), default=None)
    if widest is not None and stats[widest.lower][1] <= stats[best][1]:
        widest = None

    if precise is not None:
        options.append(_option("precise", (_contains_condition(recommended), _contains_condition(precise)), category_id, pool))
    options.append(_option("recommended", (_contains_condition(recommended),), category_id, pool))
    if widest is not None:
        options.append(_option("broad", (_contains_condition(widest),), category_id, pool))

    suggestion = SuggestionCalc(
        category_id=category_id,
        transaction_ids=tuple(t.id for t in members),
        label=recommended.display,
        ambiguous=False,
        options=tuple(options),
    )
    return suggestion, (widest or recommended)


def build_suggestions(
    corrected: list[PreviewTx],
    pool: list[PreviewTx],
    active_rules: list[RuleSpec],
) -> list[SuggestionCalc]:
    """`corrected`: movimenti che l'utente ha messo a mano nella loro categoria
    attuale (`category_id`). `pool`: tutti i movimenti del workspace per
    misurare l'impatto. Una correzione gia' coperta da una regola attiva non
    produce suggerimenti."""
    pending = [tx for tx in corrected if tx.category_id is not None and not _already_covered(active_rules, tx)]

    merchant_suggestions, used = _merchant_suggestions(pending, pool)
    by_category: dict[uuid.UUID, list[PreviewTx]] = {}
    for tx in pending:
        if tx.id not in used and tx.category_id is not None:
            by_category.setdefault(tx.category_id, []).append(tx)
    groups = sorted(
        ((cid, members) for cid, members in by_category.items() if len(members) >= THRESHOLD),
        key=lambda item: -len(item[1]),
    )[:MAX_GROUPS]

    pool_lower = [(tx, tx.text.lower()) for tx in pool]
    built: list[tuple[SuggestionCalc, _Phrase]] = []
    for category_id, members in groups:
        result = _text_suggestion(category_id, members, pool, pool_lower)
        if result is not None:
            built.append(result)

    text_suggestions: list[SuggestionCalc] = []
    for index, (suggestion, widest) in enumerate(built):
        ambiguous = False
        for other_index, (other, _) in enumerate(built):
            if other_index == index:
                continue
            other_ids = set(other.transaction_ids)
            hits = sum(1 for tx, text in pool_lower if tx.id in other_ids and widest.lower in text)
            if hits >= max(1, math.ceil(len(other_ids) / 2)):
                ambiguous = True
                break
        text_suggestions.append(
            SuggestionCalc(
                category_id=suggestion.category_id,
                transaction_ids=suggestion.transaction_ids,
                label=suggestion.label,
                ambiguous=ambiguous,
                options=suggestion.options,
            )
        )
    return merchant_suggestions + text_suggestions

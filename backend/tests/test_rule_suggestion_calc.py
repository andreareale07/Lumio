"""Suggerimenti di regola per frasi stabili. I dati sono sintetici e hanno la
struttura dei bonifici di una banca italiana: una parte che cambia (TRN), il
beneficiario e la causale scritta dall'utente."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.services.rule_preview_calc import PreviewTx
from app.services.rule_suggestion_calc import build_suggestions, phrases_of, stable_runs
from app.services.rules_engine import Condition, RuleSpec

_RATA, _GIRO, _RIST, _SENZA = (uuid.uuid4() for _ in range(4))


def _trn(i: int) -> str:
    return f"CCTX00{10000000 + i * 7919}"


def _dataset():
    pool: list[PreviewTx] = []
    corrected: list[PreviewTx] = []

    def add(desc, category, *, correct=False, merchant=None):
        tx = PreviewTx(uuid.uuid4(), date(2026, 1, 1), Decimal("-100"), desc, None, merchant, category, correct)
        pool.append(tx)
        if correct:
            corrected.append(tx)

    for i in range(12):
        category = _RATA if i not in (3, 6, 11) else (_SENZA if i == 6 else _GIRO)
        add(f"BONIFICO SEPA ISTANTANEO TRN {_trn(i)} BENEF. Reale Francesco PER Rata Mutuo", category, correct=i in (0, 1))
    for i in range(6):
        add(f"BONIFICO SEPA ISTANTANEO TRN {_trn(20 + i)} BENEF. Andrea Reale PER Conto Deposito", _GIRO, correct=i in (0, 1))
    for i in range(4):
        add(f"BONIFICO SEPA ISTANTANEO TRN {_trn(40 + i)} BENEF. Rossi Marta PER Cena", _RIST)
    for i in range(2):
        add(f"BONIFICO SEPA TRN {_trn(60 + i)} BENEF. Bianchi Luca PER Rimborso", _SENZA)
    return corrected, pool


def _by_category(suggestions, category):
    return next(s for s in suggestions if s.category_id == category)


def _option(suggestion, key):
    return next((o for o in suggestion.options if o.key == key), None)


def test_variable_tokens_break_phrases():
    runs = stable_runs("BONIFICO SEPA TRN CCTX0012 BENEF. Reale PER Rata Mutuo 487,30")
    assert runs == [["BONIFICO", "SEPA", "TRN"], ["BENEF.", "Reale", "PER", "Rata", "Mutuo"]]
    assert all("cctx" not in key for key in phrases_of("TRN CCTX0012 BENEF. Reale"))


def test_text_with_changing_numbers_still_produces_a_suggestion():
    corrected, pool = _dataset()
    rata = _by_category(build_suggestions(corrected, pool, []), _RATA)
    assert len(rata.transaction_ids) == 2
    recommended = _option(rata, "recommended")
    assert [c.value for c in recommended.conditions] == ["Rata Mutuo"]
    # I 12 movimenti del mutuo: 3 in un'altra categoria cambiano, 9 sono gia' giusti.
    assert (recommended.would_change, recommended.already_correct) == (3, 9)


def test_options_go_from_precise_to_broad():
    corrected, pool = _dataset()
    rata = _by_category(build_suggestions(corrected, pool, []), _RATA)
    precise, recommended, broad = (_option(rata, key) for key in ("precise", "recommended", "broad"))
    assert len(precise.conditions) == 2 and recommended.conditions[0] in precise.conditions
    assert broad.conditions[0].value.lower().startswith("bonifico")
    assert broad.would_change > recommended.would_change


def test_shared_phrase_across_categories_is_flagged_ambiguous():
    corrected, pool = _dataset()
    suggestions = build_suggestions(corrected, pool, [])
    assert len(suggestions) == 2
    assert all(s.ambiguous for s in suggestions)


def test_group_below_threshold_gives_no_suggestion():
    corrected, pool = _dataset()
    assert build_suggestions(corrected[:1], pool, []) == []


def test_corrections_already_covered_by_an_active_rule_are_skipped():
    corrected, pool = _dataset()
    rule = RuleSpec(
        id=uuid.uuid4(),
        conditions=(Condition(field="description", operator="contains", value="rata mutuo"),),
        category_id=_RATA,
        priority=100,
        created_at=datetime(2026, 1, 1),
    )
    categories = {s.category_id for s in build_suggestions(corrected, pool, [rule])}
    assert _RATA not in categories and _GIRO in categories


def test_merchant_corrections_produce_a_merchant_rule():
    pool = [
        PreviewTx(uuid.uuid4(), date(2026, 1, n), Decimal("-5"), f"POS {n} CAFFE ROMA", None, "Caffe Roma", _RIST, True)
        for n in (1, 2, 3)
    ]
    suggestions = build_suggestions(pool, pool, [])
    assert len(suggestions) == 1
    condition = suggestions[0].options[0].conditions[0]
    assert (condition.field, condition.operator, condition.value) == ("merchant", "merchant_equals", "Caffe Roma")


def test_a_merchant_shared_with_other_categories_falls_back_to_phrases():
    """Il merchant estratto da tutti i bonifici e' lo stesso per categorie diverse:
    non deve diventare una regola per merchant (cambierebbe categoria a quasi tutti)."""
    corrected, pool = _dataset()
    shared = "Bonifico Sepa Istantaneo Trn"
    pool = [
        PreviewTx(tx.id, tx.transaction_date, tx.amount, tx.description_raw, None, shared, tx.category_id, tx.protected)
        for tx in pool
    ]
    corrected = [tx for tx in pool if tx.id in {c.id for c in corrected}]

    suggestions = build_suggestions(corrected, pool, [])

    assert suggestions
    for suggestion in suggestions:
        for option in suggestion.options:
            assert all(condition.field != "merchant" for condition in option.conditions)
    assert [c.value for c in _option(_by_category(suggestions, _RATA), "recommended").conditions] == ["Rata Mutuo"]

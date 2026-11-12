"""Anteprima di una regola non salvata: gruppi cambiano/gia' giusti/protetti,
intervalli da evidenziare, paginazione. Funzioni pure, nessun DB."""
import uuid
from datetime import date
from decimal import Decimal

from app.services.rule_preview_calc import PreviewTx, build_preview, match_spans
from app.services.rules_engine import Condition

_TARGET = uuid.uuid4()
_OTHER = uuid.uuid4()


def _tx(text, *, category=None, protected=False, amount="-10", day=1) -> PreviewTx:
    return PreviewTx(
        id=uuid.uuid4(),
        transaction_date=date(2026, 1, day),
        amount=Decimal(amount),
        description_raw=text,
        description_normalized=None,
        merchant=None,
        category_id=category,
        protected=protected,
    )


def _contains(value) -> Condition:
    return Condition(field="description", operator="contains", value=value)


def test_matches_are_split_into_change_ok_and_protected():
    txs = [
        _tx("Rata Mutuo gennaio", category=None),
        _tx("Rata Mutuo febbraio", category=_OTHER),
        _tx("Rata Mutuo marzo", category=_TARGET),
        _tx("Rata Mutuo aprile", category=_OTHER, protected=True),
        _tx("Cena fuori", category=_OTHER),
    ]
    result = build_preview((_contains("rata mutuo"),), "all", _TARGET, txs)
    assert (result.would_change, result.already_correct, result.protected) == (2, 1, 1)
    # Dei 2 che cambierebbero, uno e' senza categoria e uno ha gia' un'altra categoria.
    assert result.recategorized == 1


def test_a_protected_transaction_already_in_the_target_category_counts_as_ok():
    txs = [_tx("Rata Mutuo", category=_TARGET, protected=True)]
    result = build_preview((_contains("rata"),), "all", _TARGET, txs)
    assert (result.would_change, result.already_correct, result.protected) == (0, 1, 0)


def test_group_filter_and_pagination_are_applied_to_items_only():
    txs = [_tx(f"Rata Mutuo {n}", category=None, day=n) for n in range(1, 6)]
    txs.append(_tx("Rata Mutuo vecchia", category=_TARGET, day=9))
    page = build_preview((_contains("rata"),), "all", _TARGET, txs, group="change", limit=2, offset=1)
    assert page.would_change == 5 and page.already_correct == 1
    assert len(page.matches) == 2
    assert all(m.group == "change" for m in page.matches)
    assert [m.tx.transaction_date.day for m in page.matches] == [4, 3]  # piu' recenti prima


def test_amount_condition_participates_in_the_match():
    txs = [_tx("Rata Mutuo", amount="-487.30"), _tx("Rata Mutuo", amount="-1200")]
    amount = Condition(field="amount", operator="between", min_amount=Decimal("450"), max_amount=Decimal("520"))
    assert build_preview((_contains("rata"), amount), "all", _TARGET, txs).would_change == 1
    assert build_preview((_contains("rata"), amount), "any", _TARGET, txs).would_change == 2


def test_spans_follow_the_engine_for_contains_and_regex():
    text = "BONIFICO SEPA TRN CCTX001 BENEF. Reale Francesco PER Rata Mutuo"
    spans = match_spans((_contains("rata mutuo"),), text)
    assert [text[a:b] for a, b in spans] == ["Rata Mutuo"]

    regex = Condition(field="description", operator="regex", value=r"cctx\d+")
    assert [text[a:b] for a, b in match_spans((regex,), text)] == ["CCTX001"]


def test_overlapping_spans_are_merged_and_amount_conditions_add_none():
    text = "Rata Mutuo casa"
    amount = Condition(field="amount", operator="between", min_amount=Decimal("1"))
    spans = match_spans((_contains("rata mu"), _contains("mutuo casa"), amount), text)
    assert [text[a:b] for a, b in spans] == ["Rata Mutuo casa"]

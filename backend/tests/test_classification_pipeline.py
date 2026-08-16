import uuid
from datetime import datetime
from decimal import Decimal

from app.services.classification_pipeline import ClassifiableRow, PipelineContext, classify_deterministic
from app.services.rules_engine import RuleSpec

_INVESTMENT_CATEGORY_ID = uuid.uuid4()
_USER_RULE_CATEGORY_ID = uuid.uuid4()

_PAC_DESCRIPTION = (
    "Savings plan execution IE00B4L5Y983 iShares III plc - iShares Core MSCI "
    "World UCITS ETF USD (Acc), quantity: 1.194268"
)


_SUPERMARKET_CATEGORY_ID = uuid.uuid4()


def _context(rules: list[RuleSpec] | None = None) -> PipelineContext:
    return PipelineContext(
        rules=rules or [],
        category_id_by_code={
            "investimenti.versamento_pac": _INVESTMENT_CATEGORY_ID,
            "alimentari.supermercato": _SUPERMARKET_CATEGORY_ID,
        },
    )


def test_pac_transaction_classified_as_system_investment_never_null():
    row = ClassifiableRow(
        description_raw=_PAC_DESCRIPTION,
        description_normalized=_PAC_DESCRIPTION,
        merchant=None,
        transaction_type="investment",
    )
    outcome = classify_deterministic(_context(), row)
    assert outcome is not None
    assert outcome.category_id == _INVESTMENT_CATEGORY_ID
    assert outcome.method == "system"
    assert outcome.score == 1


def test_user_rule_wins_over_system_type_map():
    # Una regola utente che matcha vince SEMPRE sul livello di sistema,
    # anche se la riga sarebbe altrimenti risolvibile deterministicamente
    # dal transaction_type (invariante non negoziabile del rework).
    rule = RuleSpec(
        id=uuid.uuid4(),
        field="description",
        operator="contains",
        value="iShares",
        category_id=_USER_RULE_CATEGORY_ID,
        priority=100,
        created_at=datetime(2026, 1, 1),
    )
    row = ClassifiableRow(
        description_raw=_PAC_DESCRIPTION,
        description_normalized=_PAC_DESCRIPTION,
        merchant=None,
        transaction_type="investment",
    )
    outcome = classify_deterministic(_context(rules=[rule]), row)
    assert outcome is not None
    assert outcome.category_id == _USER_RULE_CATEGORY_ID
    assert outcome.method == "rule"


def test_none_when_expected_system_category_is_missing_from_workspace():
    # La categoria "investimenti.versamento_pac" e' stata disattivata (o non
    # esiste ancora) nel workspace: nessun fallback su un'altra categoria,
    # la riga resta semplicemente non classificata a questo livello.
    ctx = PipelineContext(rules=[], category_id_by_code={})
    row = ClassifiableRow(
        description_raw=_PAC_DESCRIPTION,
        description_normalized=_PAC_DESCRIPTION,
        merchant=None,
        transaction_type="investment",
    )
    assert classify_deterministic(ctx, row) is None


def test_no_rule_no_system_match_returns_none():
    row = ClassifiableRow(
        description_raw="Pagamento generico presso terzi",
        description_normalized="Pagamento generico presso terzi",
        merchant=None,
        transaction_type="expense",
    )
    assert classify_deterministic(_context(), row) is None


def test_pattern_catalog_resolves_when_type_map_does_not():
    # LIDL non ha nulla a che vedere con transaction_type (expense e' troppo
    # generico, livello 2 restituisce None): risolve il livello 3, il
    # catalogo di pattern di sistema.
    row = ClassifiableRow(
        description_raw="PAGAMENTO POS LIDL ITALIA SRL",
        description_normalized="PAGAMENTO POS LIDL ITALIA SRL",
        merchant=None,
        transaction_type="expense",
    )
    outcome = classify_deterministic(_context(), row)
    assert outcome is not None
    assert outcome.category_id == _SUPERMARKET_CATEGORY_ID
    assert outcome.method == "system"
    assert outcome.score == Decimal("0.95")


def test_user_rule_wins_over_pattern_catalog():
    rule = RuleSpec(
        id=uuid.uuid4(),
        field="description",
        operator="contains",
        value="LIDL",
        category_id=_USER_RULE_CATEGORY_ID,
        priority=100,
        created_at=datetime(2026, 1, 1),
    )
    row = ClassifiableRow(
        description_raw="PAGAMENTO POS LIDL ITALIA SRL",
        description_normalized="PAGAMENTO POS LIDL ITALIA SRL",
        merchant=None,
        transaction_type="expense",
    )
    outcome = classify_deterministic(_context(rules=[rule]), row)
    assert outcome is not None
    assert outcome.category_id == _USER_RULE_CATEGORY_ID
    assert outcome.method == "rule"

import re
import uuid

import pytest

from app.ai.base import AIProviderError, CategoryOption
from app.ai.prompt import (
    _SYSTEM_INSTRUCTIONS_EN,
    _SYSTEM_INSTRUCTIONS_IT,
    build_messages,
    build_prompt,
    parse_response,
    response_schema,
)
from app.classification.taxonomy import TAXONOMY_BY_CODE

_GROCERIES = CategoryOption(id=uuid.uuid4(), code="groceries", name="Alimentari")
_TRANSPORT = CategoryOption(id=uuid.uuid4(), code="transport", name="Trasporti")
_CATEGORIES = [_GROCERIES, _TRANSPORT]


def test_build_prompt_lists_all_category_codes():
    from app.ai.base import ClassifiableTransaction

    transaction = ClassifiableTransaction(
        description_raw="LIDL SUPERMARKET",
        description_normalized=None,
        merchant=None,
        amount="-12.50",
        currency="EUR",
        direction="debit",
    )
    prompt = build_prompt(transaction, _CATEGORIES)
    assert "groceries" in prompt
    assert "transport" in prompt
    assert "LIDL SUPERMARKET" in prompt


def test_parse_response_matches_category_by_code():
    result = parse_response(
        '{"category_code": "groceries", "confidence": 0.8, "reason": "supermercato"}', _CATEGORIES
    )
    assert result is not None
    assert result.category_id == _GROCERIES.id
    assert result.raw_confidence == 0.8
    assert result.explanation == "supermercato"


def test_parse_response_tolerates_surrounding_text():
    result = parse_response(
        'Ecco la risposta: {"category_code": "transport", "confidence": 0.6} grazie',
        _CATEGORIES,
    )
    assert result is not None
    assert result.category_id == _TRANSPORT.id


def test_parse_response_null_category_means_no_match():
    assert parse_response('{"category_code": null, "confidence": 0.1}', _CATEGORIES) is None


def test_parse_response_unknown_code_means_no_match():
    # Il modello ha inventato un code non offerto: mai forzare una categoria
    # arbitraria (SPEC §86).
    assert parse_response('{"category_code": "invented"}', _CATEGORIES) is None


def test_parse_response_raises_on_missing_json():
    with pytest.raises(AIProviderError):
        parse_response("mi dispiace, non posso aiutarti", _CATEGORIES)


def test_parse_response_raises_on_malformed_json():
    with pytest.raises(AIProviderError):
        parse_response('{"category_code": "groceries",}', _CATEGORIES)


def test_build_messages_groups_categories_by_parent():
    from app.ai.base import ClassifiableTransaction

    child_a = CategoryOption(id=uuid.uuid4(), code="casa.affitto", name="Affitto", parent_name="Casa")
    child_b = CategoryOption(id=uuid.uuid4(), code="casa.utenze", name="Utenze", parent_name="Casa")
    other = CategoryOption(id=uuid.uuid4(), code="trasporti.carburante", name="Carburante", parent_name="Trasporti")
    transaction = ClassifiableTransaction(
        description_raw="ENI STAZIONE DI SERVIZIO",
        description_normalized=None,
        merchant=None,
        amount="-40.00",
        currency="EUR",
        direction="debit",
    )
    bundle = build_messages(transaction, [child_a, child_b, other])
    # Una sola intestazione "## Casa" (non una per figlio) e i due figli
    # elencati sotto di essa, prima del gruppo "## Trasporti".
    assert bundle.user.count("## Casa") == 1
    assert bundle.user.index("## Casa") < bundle.user.index("casa.affitto")
    assert bundle.user.index("## Casa") < bundle.user.index("casa.utenze")
    assert bundle.user.index("## Trasporti") > bundle.user.index("casa.utenze")


def test_build_messages_includes_hint_when_present():
    from app.ai.base import ClassifiableTransaction

    option = CategoryOption(
        id=uuid.uuid4(), code="trasporti.carburante", name="Carburante",
        parent_name="Trasporti", hint="benzina, diesel, GPL",
    )
    transaction = ClassifiableTransaction(
        description_raw="ENI", description_normalized=None, merchant=None,
        amount="-40.00", currency="EUR", direction="debit",
    )
    bundle = build_messages(transaction, [option])
    assert "benzina, diesel, GPL" in bundle.user


def test_build_messages_includes_new_transaction_fields():
    from app.ai.base import ClassifiableTransaction

    transaction = ClassifiableTransaction(
        description_raw="Outgoing transfer for Mario Rossi (IT99...)",
        description_normalized=None,
        merchant=None,
        amount="-100.00",
        currency="EUR",
        direction="debit",
        transaction_type="expense",
        transaction_date="2026-03-15",
        counterparty_name="Mario Rossi",
    )
    bundle = build_messages(transaction, _CATEGORIES)
    assert "2026-03-15" in bundle.user
    assert "Mario Rossi" in bundle.user
    assert "expense" in bundle.user


def test_build_prompt_is_system_plus_user_concatenation():
    from app.ai.base import ClassifiableTransaction

    transaction = ClassifiableTransaction(
        description_raw="LIDL", description_normalized=None, merchant=None,
        amount="-10.00", currency="EUR", direction="debit",
    )
    bundle = build_messages(transaction, _CATEGORIES)
    prompt = build_prompt(transaction, _CATEGORIES)
    assert prompt == f"{bundle.system}\n\n{bundle.user}"


def test_response_schema_constrains_category_code_to_offered_codes_or_null():
    schema = response_schema(_CATEGORIES)
    enum = schema["properties"]["category_code"]["enum"]
    assert set(enum) == {"groceries", "transport", None}
    assert schema["required"] == ["category_code", "confidence", "reason"]
    assert schema["additionalProperties"] is False


def test_every_few_shot_example_code_exists_in_taxonomy():
    # Un code inventato nei few-shot insegnerebbe al modello a inventarne
    # altri — ogni code citato deve esistere davvero nella tassonomia viva.
    codes = re.findall(r"-> ([a-z_]+\.[a-z_]+)\b", _SYSTEM_INSTRUCTIONS_IT)
    assert codes, "nessun code trovato nei few-shot: la regex e' rotta, non il test"
    for code in codes:
        assert code in TAXONOMY_BY_CODE, f"code {code!r} usato nei few-shot non esiste nella tassonomia"


def test_system_instructions_include_a_null_example():
    # Il modello deve imparare che astenersi e' una risposta legittima, non
    # solo che deve sempre scegliere qualcosa.
    assert "-> nessuna (null)" in _SYSTEM_INSTRUCTIONS_IT


def test_every_en_few_shot_example_code_exists_in_taxonomy():
    # Stesso controllo di test_every_few_shot_example_code_exists_in_taxonomy
    # ma per la versione inglese (fetta 2, lingua di classificazione per
    # conto) — i code restano identici in entrambe le lingue, cambia solo
    # il testo descrittivo dell'esempio.
    codes = re.findall(r"-> ([a-z_]+\.[a-z_]+)\b", _SYSTEM_INSTRUCTIONS_EN)
    assert codes, "nessun code trovato nei few-shot inglesi: la regex e' rotta, non il test"
    for code in codes:
        assert code in TAXONOMY_BY_CODE, f"code {code!r} usato nei few-shot inglesi non esiste nella tassonomia"


def test_en_system_instructions_include_a_null_example():
    assert "-> none (null)" in _SYSTEM_INSTRUCTIONS_EN


def test_build_messages_uses_english_labels_when_language_is_en():
    from app.ai.base import ClassifiableTransaction

    transaction = ClassifiableTransaction(
        description_raw="SHELL LONDON", description_normalized=None, merchant=None,
        amount="-40.00", currency="EUR", direction="debit",
    )
    bundle = build_messages(transaction, _CATEGORIES, "en")
    assert bundle.system == _SYSTEM_INSTRUCTIONS_EN
    assert "Available categories:" in bundle.user
    assert "Transaction to classify:" in bundle.user
    assert "description: SHELL LONDON" in bundle.user


def test_build_messages_defaults_to_italian_labels():
    from app.ai.base import ClassifiableTransaction

    transaction = ClassifiableTransaction(
        description_raw="LIDL", description_normalized=None, merchant=None,
        amount="-10.00", currency="EUR", direction="debit",
    )
    bundle = build_messages(transaction, _CATEGORIES)
    assert bundle.system == _SYSTEM_INSTRUCTIONS_IT
    assert "Categorie disponibili:" in bundle.user
    assert "descrizione: LIDL" in bundle.user

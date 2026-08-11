import uuid

import pytest

from app.ai.base import AIProviderError, CategoryOption
from app.ai.prompt import build_prompt, parse_response

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

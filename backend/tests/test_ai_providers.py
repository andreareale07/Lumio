"""Unit test dei provider concreti (SPEC §25-27) — nessuna rete reale, le
chiamate HTTP sono intercettate da `pytest-httpx`. Verificano solo il
trasporto (URL, header, parsing della risposta): la logica di prompt/parsing
condivisa e' gia' coperta da test_ai_prompt.py.
"""
import uuid

import httpx
import pytest

from app.ai.base import AIProviderError, CategoryOption, ClassifiableTransaction
from app.ai.providers.anthropic import AnthropicClassifier
from app.ai.providers.custom import CustomClassifier
from app.ai.providers.noai import NoAIClassifier
from app.ai.providers.ollama import OllamaClassifier
from app.ai.providers.openai import OpenAIClassifier

_CATEGORY = CategoryOption(id=uuid.uuid4(), code="groceries", name="Alimentari")
_TRANSACTION = ClassifiableTransaction(
    description_raw="LIDL",
    description_normalized=None,
    merchant=None,
    amount="-12.50",
    currency="EUR",
    direction="debit",
)


async def test_noai_never_classifies():
    classifier = NoAIClassifier()
    assert await classifier.classify(_TRANSACTION, [_CATEGORY]) is None
    await classifier.test_connection()  # non deve sollevare


async def test_ollama_classify_parses_response_field(httpx_mock):
    httpx_mock.add_response(
        url="http://ollama.local:11434/api/generate",
        json={"response": '{"category_code": "groceries", "confidence": 0.7}'},
    )
    classifier = OllamaClassifier(endpoint="http://ollama.local:11434", model="gemma3:4b")
    result = await classifier.classify(_TRANSACTION, [_CATEGORY])
    assert result is not None
    assert result.category_id == _CATEGORY.id
    request = httpx_mock.get_requests()[0]
    assert request.url.path == "/api/generate"


async def test_ollama_unreachable_raises_provider_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    classifier = OllamaClassifier(endpoint="http://ollama.local:11434", model="gemma3:4b")
    with pytest.raises(AIProviderError):
        await classifier.classify(_TRANSACTION, [_CATEGORY])


async def test_ollama_test_connection_checks_tags_endpoint(httpx_mock):
    httpx_mock.add_response(url="http://ollama.local:11434/api/tags", json={"models": []})
    classifier = OllamaClassifier(endpoint="http://ollama.local:11434", model="gemma3:4b")
    await classifier.test_connection()


async def test_openai_classify_sends_bearer_auth(httpx_mock):
    httpx_mock.add_response(
        url="https://api.openai.com/v1/chat/completions",
        json={"choices": [{"message": {"content": '{"category_code": "groceries", "confidence": 0.9}'}}]},
        match_headers={"Authorization": "Bearer sk-test"},
    )
    classifier = OpenAIClassifier(api_key="sk-test", model="gpt-4o-mini")
    result = await classifier.classify(_TRANSACTION, [_CATEGORY])
    assert result is not None
    assert result.category_id == _CATEGORY.id


async def test_openai_invalid_key_raises_provider_error(httpx_mock):
    httpx_mock.add_response(url="https://api.openai.com/v1/chat/completions", status_code=401)
    classifier = OpenAIClassifier(api_key="sk-bad", model="gpt-4o-mini")
    with pytest.raises(AIProviderError):
        await classifier.classify(_TRANSACTION, [_CATEGORY])


async def test_anthropic_classify_parses_content_block(httpx_mock):
    httpx_mock.add_response(
        url="https://api.anthropic.com/v1/messages",
        json={"content": [{"type": "text", "text": '{"category_code": "groceries", "confidence": 0.5}'}]},
        match_headers={"x-api-key": "sk-ant-test"},
    )
    classifier = AnthropicClassifier(api_key="sk-ant-test", model="claude-3-5-haiku-20241022")
    result = await classifier.classify(_TRANSACTION, [_CATEGORY])
    assert result is not None
    assert result.category_id == _CATEGORY.id


async def test_custom_classify_without_api_key_sends_no_auth_header(httpx_mock):
    httpx_mock.add_response(
        url="http://localhost:8080/v1/chat/completions",
        json={"choices": [{"message": {"content": '{"category_code": "groceries", "confidence": 0.4}'}}]},
    )
    classifier = CustomClassifier(endpoint="http://localhost:8080/v1", api_key=None, model="local-model")
    result = await classifier.classify(_TRANSACTION, [_CATEGORY])
    assert result is not None
    request = httpx_mock.get_requests()[0]
    assert "authorization" not in {k.lower() for k in request.headers.keys()}


# --- list_models -------------------------------------------------------------


async def test_noai_list_models_is_always_empty():
    assert await NoAIClassifier().list_models() == []


async def test_ollama_list_models_returns_sorted_names(httpx_mock):
    httpx_mock.add_response(
        url="http://ollama.local:11434/api/tags",
        json={"models": [{"name": "llama3.1:8b"}, {"name": "gemma3:4b"}]},
    )
    classifier = OllamaClassifier(endpoint="http://ollama.local:11434", model="")
    assert await classifier.list_models() == ["gemma3:4b", "llama3.1:8b"]


async def test_ollama_list_models_unreachable_raises(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    classifier = OllamaClassifier(endpoint="http://ollama.local:11434", model="")
    with pytest.raises(AIProviderError):
        await classifier.list_models()


async def test_openai_list_models_filters_non_text_models(httpx_mock):
    httpx_mock.add_response(
        url="https://api.openai.com/v1/models",
        json={
            "data": [
                {"id": "gpt-4o-mini"},
                {"id": "whisper-1"},
                {"id": "text-embedding-3-small"},
                {"id": "gpt-4o"},
            ]
        },
    )
    classifier = OpenAIClassifier(api_key="sk-test", model="")
    models = await classifier.list_models()
    assert set(models) == {"gpt-4o-mini", "gpt-4o"}


async def test_anthropic_list_models_returns_ids_as_is(httpx_mock):
    httpx_mock.add_response(
        url="https://api.anthropic.com/v1/models",
        json={"data": [{"id": "claude-3-5-haiku-20241022"}, {"id": "claude-3-5-sonnet-20241022"}]},
    )
    classifier = AnthropicClassifier(api_key="sk-ant-test", model="")
    models = await classifier.list_models()
    assert models == ["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"]


async def test_custom_list_models_returns_empty_on_failure_instead_of_raising(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    classifier = CustomClassifier(endpoint="http://localhost:8080/v1", api_key=None, model="")
    assert await classifier.list_models() == []


async def test_custom_list_models_returns_ids_when_supported(httpx_mock):
    httpx_mock.add_response(
        url="http://localhost:8080/v1/models", json={"data": [{"id": "local-model-a"}]}
    )
    classifier = CustomClassifier(endpoint="http://localhost:8080/v1", api_key=None, model="")
    assert await classifier.list_models() == ["local-model-a"]

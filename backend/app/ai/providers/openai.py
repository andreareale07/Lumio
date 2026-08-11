"""Provider AI cloud OpenAI (SPEC §27). L'utente fornisce la propria API
key, mai richiesta per il funzionamento base dell'app. `response_format:
json_object` forza l'output a JSON valido lato server, coerente con
`app/ai/prompt.parse_response`.
"""
import httpx

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction
from app.ai.prompt import build_prompt, parse_response
from app.core.config import get_settings

_BASE_URL = "https://api.openai.com/v1"

# `GET /models` elenca TUTTI i modelli OpenAI (anche whisper/tts/embedding/
# immagini, inutilizzabili per la classificazione testuale di questo
# provider) — filtro per famiglia, non per un modello specifico: non lega
# l'app a un nome di modello esatto (coerente con SPEC §26/§82), esclude
# solo cio' che non e' un modello di chat/testo.
_NON_TEXT_MODEL_MARKERS = ("whisper", "tts", "embedding", "dall-e", "moderation", "davinci-002", "babbage")


class OpenAIClassifier:
    provider = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model or "gpt-4o-mini"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def classify(
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption]
    ) -> AIClassificationResult | None:
        settings = get_settings()
        prompt = build_prompt(transaction, categories)
        try:
            async with httpx.AsyncClient(timeout=settings.ai_classify_timeout_seconds) as client:
                response = await client.post(
                    f"{_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"OpenAI non raggiungibile o credenziali non valide: {exc}") from exc

        body = response.json()
        try:
            raw_text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(f"risposta OpenAI inattesa: {body}") from exc
        return parse_response(raw_text, categories)

    async def test_connection(self) -> None:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{_BASE_URL}/models", headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"OpenAI non raggiungibile o credenziali non valide: {exc}") from exc

    async def list_models(self) -> list[str]:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{_BASE_URL}/models", headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"OpenAI non raggiungibile o credenziali non valide: {exc}") from exc

        body = response.json()
        ids = [m["id"] for m in body.get("data", []) if isinstance(m, dict) and m.get("id")]
        text_ids = [i for i in ids if not any(marker in i for marker in _NON_TEXT_MODEL_MARKERS)]
        return sorted(text_ids, reverse=True)

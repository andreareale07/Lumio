"""Provider AI cloud OpenAI (SPEC §27). L'utente fornisce la propria API
key, mai richiesta per il funzionamento base dell'app.

Rework prompt AI: tenta prima `response_format: json_schema` (structured
output nativo, vincola `category_code` a un enum dei code offerti — il
modello non puo' proprio inventarne uno dove questo e' rispettato); su 400
(modello/versione senza supporto) ripiega su `json_object`, che tutti i
modelli chat OpenAI supportano. `parse_response` resta comunque l'unica
difesa reale contro un code inventato quando lo schema non e' rispettato.
"""
import httpx

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction
from app.ai.http_retry import post_with_retry
from app.ai.prompt import build_messages, parse_response, response_schema
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
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption], language: str = "it"
    ) -> AIClassificationResult | None:
        settings = get_settings()
        bundle = build_messages(transaction, categories, language)
        messages = [
            {"role": "system", "content": bundle.system},
            {"role": "user", "content": bundle.user},
        ]
        schema_response_format = {
            "type": "json_schema",
            "json_schema": {"name": "classificazione", "strict": True, "schema": response_schema(categories)},
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ai_classify_timeout_seconds) as client:
                response = await post_with_retry(
                    client,
                    f"{_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json={"model": self.model, "messages": messages, "response_format": schema_response_format},
                )
                if response.status_code == 400:
                    # Modello/versione senza supporto per json_schema
                    # strutturato: fallback al formato libero, supportato
                    # da tutti i modelli chat OpenAI.
                    response = await post_with_retry(
                        client,
                        f"{_BASE_URL}/chat/completions",
                        headers=self._headers(),
                        json={
                            "model": self.model,
                            "messages": messages,
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

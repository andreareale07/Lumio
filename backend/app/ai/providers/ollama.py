"""Provider AI locale (SPEC §26). Endpoint configurabile, nessun modello
specifico assunto (SPEC: "l'applicazione non deve essere legata a Gemma").
Usa `/api/generate` con `format: "json"` (Ollama forza l'output a JSON
valido lato server quando supportato dal modello) invece di `/api/chat`:
un solo prompt di testo e' sufficiente per questo caso d'uso, niente
gestione di history conversazionale.
"""
import httpx

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction
from app.ai.prompt import build_prompt, parse_response
from app.core.config import get_settings


class OllamaClassifier:
    provider = "ollama"

    def __init__(self, endpoint: str, model: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model

    async def classify(
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption]
    ) -> AIClassificationResult | None:
        settings = get_settings()
        prompt = build_prompt(transaction, categories)
        try:
            async with httpx.AsyncClient(timeout=settings.ai_classify_timeout_seconds) as client:
                response = await client.post(
                    f"{self.endpoint}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False, "format": "json"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Ollama non raggiungibile: {exc}") from exc

        body = response.json()
        raw_text = body.get("response", "")
        return parse_response(raw_text, categories)

    async def test_connection(self) -> None:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{self.endpoint}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Ollama non raggiungibile: {exc}") from exc

    async def list_models(self) -> list[str]:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{self.endpoint}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Ollama non raggiungibile: {exc}") from exc

        body = response.json()
        names = [m["name"] for m in body.get("models", []) if isinstance(m, dict) and m.get("name")]
        return sorted(names)

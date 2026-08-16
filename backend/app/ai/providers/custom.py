"""Server personalizzato OpenAI-compatible (SPEC §25: "Custom HTTP
endpoint"). Copre self-hosted come vLLM/LM Studio/text-generation-webui che
espongono l'API `/chat/completions` di OpenAI. `api_key` e' opzionale (molti
setup locali non ne richiedono una) — se assente, nessun header
Authorization viene inviato invece di mandarne uno vuoto/finto.

Rework prompt AI: system+user come messaggi separati (formato standard
OpenAI-compatible, supportato da tutti i backend elencati sopra) — ma
NESSUN tentativo di structured output/JSON Schema: un endpoint arbitrario
non da' garanzie su quali estensioni supporti, meglio restare sul
formato-prompt robusto (`parse_response` estrae comunque il JSON da testo
libero) che rischiare una richiesta che il server non sa interpretare.
"""
import httpx

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction
from app.ai.http_retry import post_with_retry
from app.ai.prompt import build_messages, parse_response
from app.core.config import get_settings


class CustomClassifier:
    provider = "custom"

    def __init__(self, endpoint: str, api_key: str | None, model: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def classify(
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption]
    ) -> AIClassificationResult | None:
        settings = get_settings()
        bundle = build_messages(transaction, categories)
        messages = [
            {"role": "system", "content": bundle.system},
            {"role": "user", "content": bundle.user},
        ]
        try:
            async with httpx.AsyncClient(timeout=settings.ai_classify_timeout_seconds) as client:
                response = await post_with_retry(
                    client,
                    f"{self.endpoint}/chat/completions",
                    headers=self._headers(),
                    json={"model": self.model, "messages": messages},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"server personalizzato non raggiungibile: {exc}") from exc

        body = response.json()
        try:
            raw_text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(f"risposta del server personalizzato inattesa: {body}") from exc
        return parse_response(raw_text, categories)

    async def test_connection(self) -> None:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{self.endpoint}/models", headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"server personalizzato non raggiungibile: {exc}") from exc

    async def list_models(self) -> list[str]:
        # A differenza di Ollama/OpenAI/Anthropic, un server "personalizzato"
        # non garantisce di implementare `/models` (non tutti i backend
        # OpenAI-compatible lo fanno) — qui il best-effort fallisce in
        # silenzio (lista vuota) invece di sollevare, cosi' la UI ricade sul
        # campo di testo libero senza mostrare un errore per una feature
        # opzionale su un provider che promette solo `/chat/completions`.
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{self.endpoint}/models", headers=self._headers())
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError):
            return []

        return [m["id"] for m in body.get("data", []) if isinstance(m, dict) and m.get("id")]

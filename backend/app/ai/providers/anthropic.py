"""Provider AI cloud Anthropic (SPEC §27). Stesso principio di
`OpenAIClassifier`: chiave fornita dall'utente, mai richiesta per il
funzionamento base. La Messages API non supporta un `response_format`
strutturato generico come OpenAI: ci si affida al prompt ("rispondi SOLO con
JSON") + `parse_response`, che estrae comunque il primo blocco `{...}`
dalla risposta anche se il modello aggiunge testo attorno.
"""
import httpx

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction
from app.ai.prompt import build_prompt, parse_response
from app.core.config import get_settings

_BASE_URL = "https://api.anthropic.com/v1"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicClassifier:
    provider = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model or "claude-3-5-haiku-20241022"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }

    async def classify(
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption]
    ) -> AIClassificationResult | None:
        settings = get_settings()
        prompt = build_prompt(transaction, categories)
        try:
            async with httpx.AsyncClient(timeout=settings.ai_classify_timeout_seconds) as client:
                response = await client.post(
                    f"{_BASE_URL}/messages",
                    headers=self._headers(),
                    json={
                        "model": self.model,
                        "max_tokens": 300,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Anthropic non raggiungibile o credenziali non valide: {exc}") from exc

        body = response.json()
        try:
            raw_text = body["content"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(f"risposta Anthropic inattesa: {body}") from exc
        return parse_response(raw_text, categories)

    async def test_connection(self) -> None:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{_BASE_URL}/models", headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Anthropic non raggiungibile o credenziali non valide: {exc}") from exc

    async def list_models(self) -> list[str]:
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.ai_test_timeout_seconds) as client:
                response = await client.get(f"{_BASE_URL}/models", headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Anthropic non raggiungibile o credenziali non valide: {exc}") from exc

        body = response.json()
        # L'API restituisce gia' i modelli piu' recenti per primi, nessun
        # riordino necessario (a differenza di OpenAI, qui sono tutti
        # modelli di chat testuale — nessun filtro per famiglia richiesto).
        return [m["id"] for m in body.get("data", []) if isinstance(m, dict) and m.get("id")]

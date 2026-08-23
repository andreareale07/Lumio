"""Provider AI cloud Anthropic (SPEC §27). Stesso principio di
`OpenAIClassifier`: chiave fornita dall'utente, mai richiesta per il
funzionamento base.

Rework prompt AI: la Messages API non ha un `response_format` strutturato
generico come OpenAI, ma supporta tool-use forzato (`tool_choice`) — usato
qui per ottenere un JSON strutturato direttamente come `input` del tool,
senza bisogno di estrarlo per regex da testo libero. Se il modello non
produce un blocco `tool_use` (versione/modello senza supporto, o un
comportamento inatteso), si ripiega sull'estrazione testuale via
`parse_response`, stesso percorso robusto degli altri provider.
"""
import httpx

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction
from app.ai.http_retry import post_with_retry
from app.ai.prompt import build_messages, parse_payload, parse_response, response_schema
from app.core.config import get_settings

_BASE_URL = "https://api.anthropic.com/v1"
_ANTHROPIC_VERSION = "2023-06-01"
_TOOL_NAME = "classifica_transazione"


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
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption], language: str = "it"
    ) -> AIClassificationResult | None:
        settings = get_settings()
        bundle = build_messages(transaction, categories, language)
        tool = {
            "name": _TOOL_NAME,
            "description": "Classifica la transazione in una delle categorie offerte.",
            "input_schema": response_schema(categories),
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ai_classify_timeout_seconds) as client:
                response = await post_with_retry(
                    client,
                    f"{_BASE_URL}/messages",
                    headers=self._headers(),
                    json={
                        "model": self.model,
                        "max_tokens": 300,
                        "system": bundle.system,
                        "messages": [{"role": "user", "content": bundle.user}],
                        "tools": [tool],
                        "tool_choice": {"type": "tool", "name": _TOOL_NAME},
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Anthropic non raggiungibile o credenziali non valide: {exc}") from exc

        body = response.json()
        content = body.get("content", [])
        tool_use = next(
            (block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"), None
        )
        if tool_use is not None:
            return parse_payload(tool_use.get("input", {}), categories)

        # Fallback: nessun blocco tool_use nella risposta (modello/versione
        # senza supporto per tool forzato) — stesso percorso robusto degli
        # altri provider, estrazione JSON da testo libero.
        text_block = next(
            (block for block in content if isinstance(block, dict) and block.get("type") == "text"), None
        )
        if text_block is None:
            raise AIProviderError(f"risposta Anthropic senza contenuto utile: {body}")
        return parse_response(text_block["text"], categories)

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

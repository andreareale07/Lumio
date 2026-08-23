"""Provider di default (SPEC §25: "l'app deve funzionare completamente anche
con AI disabled"). Sempre disponibile, nessuna configurazione richiesta."""
from app.ai.base import AIClassificationResult, CategoryOption, ClassifiableTransaction


class NoAIClassifier:
    provider = "none"

    async def classify(
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption], language: str = "it"
    ) -> AIClassificationResult | None:
        return None

    async def test_connection(self) -> None:
        return None

    async def list_models(self) -> list[str]:
        return []

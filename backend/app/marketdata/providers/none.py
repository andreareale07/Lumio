"""Provider di default (SPEC §38: "se il market data provider non e'
configurato, l'applicazione deve continuare a funzionare"). Sempre
disponibile, nessuna configurazione richiesta — stesso ruolo di
`NoAIClassifier` in M07."""
from app.marketdata.base import AssetRef, Quote


class NoMarketDataProvider:
    provider = "none"

    async def fetch_quote(self, asset: AssetRef) -> Quote | None:
        return None

    async def test_connection(self) -> None:
        return None

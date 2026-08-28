"""Provider di default (SPEC §38: "se il market data provider non e'
configurato, l'applicazione deve continuare a funzionare"). Sempre
disponibile, nessuna configurazione richiesta — stesso ruolo di
`NoAIClassifier` in M07."""
from datetime import date

from app.marketdata.base import AssetProfile, AssetRef, FxQuote, PricePoint, Quote


class NoMarketDataProvider:
    provider = "none"

    async def fetch_quote(self, asset: AssetRef) -> Quote | None:
        return None

    async def test_connection(self) -> None:
        return None

    async def fetch_history(self, asset: AssetRef, preset: str) -> list[PricePoint] | None:
        return None

    async def fetch_profile(self, asset: AssetRef) -> AssetProfile | None:
        return None

    async def fetch_fx_rate(self, from_currency: str, to_currency: str) -> FxQuote | None:
        return None

    async def fetch_fx_history(
        self, from_currency: str, to_currency: str, preset: str
    ) -> list[PricePoint] | None:
        return None

    async def fetch_history_range(
        self, asset: AssetRef, date_from: date, date_to: date
    ) -> list[PricePoint] | None:
        return None

    async def fetch_fx_history_range(
        self, from_currency: str, to_currency: str, date_from: date, date_to: date
    ) -> list[PricePoint] | None:
        return None

"""Profilo "manuale" (SPEC §38: "dati manuali" e' uno dei backend previsti
per `MarketDataProvider"). Non fa mai fetch automatico: esiste solo perche'
l'utente possa dichiarare esplicitamente "aggiorno i prezzi a mano" invece di
lasciare il market data disattivato — l'inserimento vero avviene tramite
`POST /assets/{id}/prices` (sempre disponibile, indipendentemente dal
profilo attivo), non da questa classe. `fetch_quote` ritorna sempre `None`:
non c'e' nulla da scaricare, il job di refresh automatico salta semplicemente
gli asset quando questo e' il profilo attivo."""
from app.marketdata.base import AssetProfile, AssetRef, FxQuote, PricePoint, Quote


class ManualMarketDataProvider:
    provider = "manual"

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

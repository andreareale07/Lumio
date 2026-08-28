"""Provider generico configurabile (SPEC §85 "provider agnostic"): copre
Alpha Vantage / Twelve Data / Finnhub e simili senza hardcodare nessun
servizio specifico. L'utente fornisce un URL con placeholder `{symbol}`,
un'API key opzionale (inviata come query param `apikey`, convenzione piu'
comune tra questi servizi) e due percorsi puntati per estrarre prezzo e
valuta dalla risposta JSON (es. "price" o "quote.price").
"""
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from app.marketdata.base import AssetProfile, AssetRef, FxQuote, MarketDataProviderError, PricePoint, Quote

_TIMEOUT = 10.0


def _resolve_path(data: object, path: str) -> object | None:
    current = data
    for part in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


class CustomProvider:
    provider = "custom"

    def __init__(
        self, endpoint: str, api_key: str | None, price_field: str, currency_field: str | None
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.price_field = price_field
        self.currency_field = currency_field

    def _url(self, symbol: str) -> str:
        return self.endpoint.replace("{symbol}", symbol)

    async def _get(self, symbol: str) -> httpx.Response:
        if not self.endpoint:
            raise MarketDataProviderError("Endpoint non configurato")
        params = {"apikey": self.api_key} if self.api_key else None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(self._url(symbol), params=params)
                response.raise_for_status()
                return response
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Provider custom non raggiungibile: {exc}") from exc

    async def fetch_quote(self, asset: AssetRef) -> Quote | None:
        if not asset.symbol or not self.endpoint:
            return None
        response = await self._get(asset.symbol)
        try:
            body = response.json()
        except ValueError:
            return None

        raw_price = _resolve_path(body, self.price_field)
        if raw_price is None:
            return None
        try:
            price = Decimal(str(raw_price))
        except InvalidOperation:
            return None

        currency = asset.currency
        if self.currency_field:
            raw_currency = _resolve_path(body, self.currency_field)
            if isinstance(raw_currency, str) and raw_currency:
                currency = raw_currency
        return Quote(price=price, currency=currency, as_of=date.today())

    async def test_connection(self) -> None:
        # Nessun asset specifico da testare qui: si usa un simbolo di prova
        # ("AAPL") solo per verificare che l'endpoint risponda —
        # best-effort, non garantisce che TUTTI gli asset configurati siano
        # risolvibili (va segnalato in UI).
        await self._get("AAPL")

    async def fetch_history(self, asset: AssetRef, preset: str) -> list[PricePoint] | None:
        # Un endpoint custom e' definito per una singola quotazione (un
        # campo prezzo per risposta) — nessuna convenzione generica per uno
        # storico su un servizio arbitrario configurato dall'utente.
        return None

    async def fetch_profile(self, asset: AssetRef) -> AssetProfile | None:
        return None

    async def fetch_fx_rate(self, from_currency: str, to_currency: str) -> FxQuote | None:
        # Un endpoint custom e' definito per un asset (URL con {symbol}) —
        # nessuna convenzione generica per una coppia di valute.
        return None

    async def fetch_fx_history(
        self, from_currency: str, to_currency: str, preset: str
    ) -> list[PricePoint] | None:
        return None

    async def fetch_history_range(
        self, asset: AssetRef, date_from: date, date_to: date
    ) -> list[PricePoint] | None:
        # Stesso limite di fetch_history: un endpoint custom e' definito per
        # una singola quotazione, nessuna convenzione generica per uno
        # storico su un servizio arbitrario configurato dall'utente.
        return None

    async def fetch_fx_history_range(
        self, from_currency: str, to_currency: str, date_from: date, date_to: date
    ) -> list[PricePoint] | None:
        return None

"""Provider gratuito senza registrazione (SPEC §38), endpoint NON ufficiale
("chart" API pubblica usata anche da yahoo finance stesso, mai documentata
né garantita — da segnalare come best-effort in UI). Nessuna API key.
Richiede uno User-Agent da browser: senza, Yahoo risponde 429/999 anche
senza aver superato alcun limite dichiarato.
"""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.marketdata.base import AssetRef, MarketDataProviderError, Quote

_CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_SEARCH_ENDPOINT = "https://query1.finance.yahoo.com/v1/finance/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Lumio/1.0)"}
_TIMEOUT = 10.0


class YahooProvider:
    provider = "yahoo"

    async def fetch_quote(self, asset: AssetRef) -> Quote | None:
        symbol = asset.symbol
        if not symbol:
            if not asset.isin:
                return None
            # L'endpoint "chart" NON risolve un ISIN diretto (verificato: un
            # ISIN passato come {symbol} risponde "No data found, symbol may
            # be delisted") — serve prima risolverlo a un ticker Yahoo reale
            # via l'endpoint di ricerca (che l'ISIN lo accetta davvero).
            symbol = await self._resolve_symbol_from_isin(asset.isin)
            if symbol is None:
                return None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                response = await client.get(_CHART_ENDPOINT.format(symbol=symbol))
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Yahoo Finance non raggiungibile: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            return None

        results = ((body.get("chart") or {}).get("result")) or []
        if not results:
            return None
        meta = results[0].get("meta") or {}
        raw_price = meta.get("regularMarketPrice")
        if raw_price is None:
            return None
        try:
            price = Decimal(str(raw_price))
        except InvalidOperation:
            return None

        timestamp = meta.get("regularMarketTime")
        quote_date = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc).date() if timestamp else date.today()
        )
        currency = meta.get("currency") or asset.currency
        return Quote(price=price, currency=currency, as_of=quote_date)

    async def _resolve_symbol_from_isin(self, isin: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                response = await client.get(_SEARCH_ENDPOINT, params={"q": isin})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Yahoo Finance non raggiungibile: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            return None
        quotes = body.get("quotes") or []
        if not quotes:
            return None
        return quotes[0].get("symbol") or None

    async def test_connection(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                response = await client.get(_CHART_ENDPOINT.format(symbol="AAPL"))
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Yahoo Finance non raggiungibile: {exc}") from exc

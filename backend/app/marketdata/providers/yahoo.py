"""Provider gratuito senza registrazione (SPEC §38), endpoint NON ufficiale
("chart" API pubblica usata anche da yahoo finance stesso, mai documentata
né garantita — da segnalare come best-effort in UI). Nessuna API key.
Richiede uno User-Agent da browser: senza, Yahoo risponde 429/999 anche
senza aver superato alcun limite dichiarato.
"""
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx

from app.marketdata.base import AssetProfile, AssetRef, FxQuote, MarketDataProviderError, PricePoint, Quote

_CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_SEARCH_ENDPOINT = "https://query1.finance.yahoo.com/v1/finance/search"
# `quoteSummary` (usato solo da `fetch_profile`) pretende un cookie+crumb dal
# 2023 — a differenza di "chart"/"search", non risponde piu' senza (SPEC
# Step 3: "si rompe spesso", da qui il fetch a due passi sotto).
_COOKIE_ENDPOINT = "https://fc.yahoo.com"
_CRUMB_ENDPOINT = "https://query1.finance.yahoo.com/v1/test/getcrumb"
_QUOTE_SUMMARY_ENDPOINT = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Lumio/1.0)"}
_TIMEOUT = 10.0

# Preset -> (range, interval) di Yahoo (SPEC "storico prezzi asset"). Quali
# preset vengono anche persistiti in `asset_prices` e' deciso dal chiamante
# (`app/api/v1/assets.py::HISTORY_PRESETS`), non da questo provider — qui si
# traduce solo il preset nella chiamata Yahoo corretta.
_RANGE_INTERVAL: dict[str, tuple[str, str]] = {
    "1G": ("1d", "5m"),
    "1S": ("5d", "30m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1A": ("1y", "1d"),
    "5A": ("5y", "1wk"),
    "Max": ("max", "1mo"),
}


def _extract_raw_decimal(field: object) -> Decimal | None:
    """I campi numerici di `quoteSummary` sono oggetti `{"raw": ..., "fmt":
    ...}`, mai un numero nudo — un formato assente o inatteso e' un dato
    mancante, non un errore."""
    if not isinstance(field, dict):
        return None
    raw = field.get("raw")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return None


def _infer_distribution_policy(long_name: str | None) -> str | None:
    """Accumulo/distribuzione NON e' un campo Yahoo — si deduce dal nome del
    fondo (SPEC Step 3: "mai uno stato certo"). Cerca "Acc"/"Dist" come
    parola intera (tra spazi, parentesi o a fine stringa) per non scambiare
    per errore un emittente il cui nome contiene "acc"/"dist" come
    sottostringa (es. "Accenture")."""
    if not long_name:
        return None
    if re.search(r"(?i)(?:^|[\s(])acc(?:umulat\w*)?(?:[\s)]|$)", long_name):
        return "accumulating"
    if re.search(r"(?i)(?:^|[\s(])dist(?:ribut\w*)?(?:[\s)]|$)", long_name):
        return "distributing"
    return None


class YahooProvider:
    provider = "yahoo"

    async def fetch_quote(self, asset: AssetRef) -> Quote | None:
        symbol = await self._resolve_symbol(asset)
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

    async def _resolve_symbol(self, asset: AssetRef) -> str | None:
        if asset.symbol:
            return asset.symbol
        if not asset.isin:
            return None
        # L'endpoint "chart" NON risolve un ISIN diretto (verificato: un
        # ISIN passato come {symbol} risponde "No data found, symbol may be
        # delisted") — serve prima risolverlo a un ticker Yahoo reale via
        # l'endpoint di ricerca (che l'ISIN lo accetta davvero).
        return await self._resolve_symbol_from_isin(asset.isin)

    async def fetch_history(self, asset: AssetRef, preset: str) -> list[PricePoint] | None:
        range_interval = _RANGE_INTERVAL.get(preset)
        if range_interval is None:
            return None
        symbol = await self._resolve_symbol(asset)
        if symbol is None:
            return None
        range_, interval = range_interval

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                response = await client.get(
                    _CHART_ENDPOINT.format(symbol=symbol),
                    params={"range": range_, "interval": interval},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Yahoo Finance non raggiungibile: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            return []

        results = ((body.get("chart") or {}).get("result")) or []
        if not results:
            return []
        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quotes.get("close") or []

        points: list[PricePoint] = []
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            try:
                price = Decimal(str(close))
            except InvalidOperation:
                continue
            at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            points.append(PricePoint(at=at, price=price))
        return points

    async def fetch_profile(self, asset: AssetRef) -> AssetProfile | None:
        symbol = await self._resolve_symbol(asset)
        if symbol is None:
            return None
        # Nessuna eccezione propagata da qui in poi (contratto diverso da
        # fetch_quote/fetch_history, vedi base.py): un 401 sul crumb, un
        # campo mancante o una risposta inattesa risultano tutti in `None`,
        # mai un errore che romperebbe la pagina di dettaglio asset.
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
                await client.get(_COOKIE_ENDPOINT)
                crumb_response = await client.get(_CRUMB_ENDPOINT)
                crumb_response.raise_for_status()
                crumb = crumb_response.text.strip()

                response = await client.get(
                    _QUOTE_SUMMARY_ENDPOINT.format(symbol=symbol),
                    params={
                        "modules": "quoteType,fundProfile,summaryDetail",
                        "crumb": crumb,
                    },
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        results = ((body.get("quoteSummary") or {}).get("result")) or []
        if not results:
            return None
        result = results[0]

        quote_type = result.get("quoteType") or {}
        fund_profile = result.get("fundProfile") or {}
        summary_detail = result.get("summaryDetail") or {}

        long_name = quote_type.get("longName") or quote_type.get("shortName")
        # "Emittente" ha senso solo per un fondo/ETF (chi lo gestisce, es.
        # "Vanguard") — SOLO da `fundProfile.family`, mai da
        # `summaryProfile.industry` (il settore industriale di un'azienda,
        # es. "Consumer Electronics" per Apple: un campo semanticamente
        # diverso, bug osservato in verifica manuale). Per un'azione singola
        # `fundProfile` e' vuoto e l'emittente resta `None`, correttamente.
        issuer = fund_profile.get("family")
        category = fund_profile.get("categoryName")
        aum = _extract_raw_decimal(summary_detail.get("totalAssets"))

        return AssetProfile(
            issuer=issuer,
            category=category,
            aum=aum,
            distribution_policy=_infer_distribution_policy(long_name),
            # Nome "pulito" secondo Yahoo (es. "Apple Inc.") — mai una
            # sovrascrittura di Asset.name, vedi docstring di AssetProfile.
            display_name=long_name,
        )

    async def fetch_fx_rate(self, from_currency: str, to_currency: str) -> FxQuote | None:
        # Stesso endpoint "chart" di fetch_quote, simbolo di cambio Yahoo
        # (es. "USDEUR=X") invece di un ticker asset — nessuna infrastruttura
        # nuova, nessuna risoluzione ISIN/simbolo da fare.
        symbol = f"{from_currency}{to_currency}=X"
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
        raw_rate = meta.get("regularMarketPrice")
        if raw_rate is None:
            return None
        try:
            rate = Decimal(str(raw_rate))
        except InvalidOperation:
            return None

        timestamp = meta.get("regularMarketTime")
        as_of = datetime.fromtimestamp(timestamp, tz=timezone.utc).date() if timestamp else date.today()
        return FxQuote(rate=rate, as_of=as_of)

    async def fetch_fx_history(
        self, from_currency: str, to_currency: str, preset: str
    ) -> list[PricePoint] | None:
        range_interval = _RANGE_INTERVAL.get(preset)
        if range_interval is None:
            return None
        range_, interval = range_interval
        symbol = f"{from_currency}{to_currency}=X"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                response = await client.get(
                    _CHART_ENDPOINT.format(symbol=symbol),
                    params={"range": range_, "interval": interval},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Yahoo Finance non raggiungibile: {exc}") from exc

        try:
            body = response.json()
        except ValueError:
            return []

        results = ((body.get("chart") or {}).get("result")) or []
        if not results:
            return []
        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quotes.get("close") or []

        points: list[PricePoint] = []
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            try:
                rate = Decimal(str(close))
            except InvalidOperation:
                continue
            at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            points.append(PricePoint(at=at, price=rate))
        return points

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

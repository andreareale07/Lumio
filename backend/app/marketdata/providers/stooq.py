"""Provider gratuito senza registrazione (SPEC §38: provider "gratuiti").
Endpoint CSV pubblico di Stooq — nessuna API key. Limite noto, documentato
in UI: il `symbol` deve essere gia' nel formato riconosciuto da Stooq (es.
`VWCE.UK`, non solo `VWCE`); Lumio non fa alcun mapping automatico ISIN/
ticker→simbolo Stooq. Nessuna valuta nella risposta: si assume quella
dell'asset (coerente col principio "nessuna conversione valutaria",
app/services/analytics.py).

STATO VERIFICATO (agosto 2026, chiamata reale): Stooq ha introdotto una
sfida JavaScript anti-bot davanti a tutto il sito (anche alla home page,
non solo all'endpoint quotazioni) — un client HTTP semplice come questo
riceve un 404 (nessuna eccezione non gestita: `test_connection`/
`fetch_quote` lo riportano onestamente come "non raggiungibile", mai un
crash). Codice lasciato cosi' com'e': se Stooq rimuove la protezione in
futuro, torna a funzionare senza modifiche. Non e' stato implementato
nessun tentativo di superare la sfida (fuori scope, e comunque contrario
al principio "nessuna evasione di sistemi di rilevamento").
"""
import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.marketdata.base import AssetProfile, AssetRef, FxQuote, MarketDataProviderError, PricePoint, Quote

_QUOTE_ENDPOINT = "https://stooq.com/q/l/"
_TIMEOUT = 10.0


class StooqProvider:
    provider = "stooq"

    async def fetch_quote(self, asset: AssetRef) -> Quote | None:
        if not asset.symbol:
            return None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    _QUOTE_ENDPOINT, params={"s": asset.symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"}
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Stooq non raggiungibile: {exc}") from exc

        row = next(csv.DictReader(io.StringIO(response.text)), None)
        # "N/D" e' la convenzione di Stooq per un simbolo non trovato — non
        # un errore di comunicazione, un dato assente (DoD M09).
        if row is None or row.get("Close") in (None, "N/D", ""):
            return None
        try:
            price = Decimal(row["Close"])
            quote_date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
        except (KeyError, InvalidOperation, ValueError):
            return None
        return Quote(price=price, currency=asset.currency, as_of=quote_date)

    async def test_connection(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get("https://stooq.com")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataProviderError(f"Stooq non raggiungibile: {exc}") from exc

    async def fetch_history(self, asset: AssetRef, preset: str) -> list[PricePoint] | None:
        # L'endpoint CSV di Stooq usato per la quotazione corrente non offre
        # uno storico — non implementato (a differenza di Yahoo, non c'e' un
        # endpoint "chart" pubblico equivalente gia' verificato).
        return None

    async def fetch_profile(self, asset: AssetRef) -> AssetProfile | None:
        return None

    async def fetch_fx_rate(self, from_currency: str, to_currency: str) -> FxQuote | None:
        # Nessun endpoint FX pubblico di Stooq verificato (stesso limite
        # gia' accettato per fetch_history) — non implementato.
        return None

    async def fetch_fx_history(
        self, from_currency: str, to_currency: str, preset: str
    ) -> list[PricePoint] | None:
        return None

    async def fetch_history_range(
        self, asset: AssetRef, date_from: date, date_to: date
    ) -> list[PricePoint] | None:
        # Stesso limite di fetch_history: nessun endpoint storico Stooq
        # pubblico verificato.
        return None

    async def fetch_fx_history_range(
        self, from_currency: str, to_currency: str, date_from: date, date_to: date
    ) -> list[PricePoint] | None:
        return None

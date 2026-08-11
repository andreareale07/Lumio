"""Interfaccia astratta del provider di quotazioni (SPEC §38:
`MarketDataProvider`). Stesso pattern di `AIClassifier` (app/ai/base.py) e
`BankParser`: un `Protocol` strutturale, non una classe base da ereditare.

Il vincolo di prodotto (ROADMAP M09 DoD, SPEC §38) e' identico a quello
dell'AI in M07: "se il market data provider non e' configurato, l'app deve
continuare a funzionare" — `profile=None` risolve sempre a
`NoMarketDataProvider`, mai un errore (vedi `app/marketdata/registry.py`).

Nota architetturale: questo provider serve solo a POPOLARE `asset_prices`
con nuove quotazioni (job schedulato o refresh manuale, vedi
`app/worker/jobs/market_data.py`). La lettura dei prezzi per la
valorizzazione delle posizioni (`app/services/portfolio_analytics.py`) legge
SEMPRE da `asset_prices`, mai direttamente dal provider — cosi' un prezzo
gia' scaricato resta disponibile anche se il provider va offline o il
profilo viene disattivato, e lo storico prezzi si accumula giorno per
giorno indipendentemente da chi lo ha scritto (fetch automatico o
inserimento manuale, stessa tabella, `source` diverso).
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class AssetRef:
    """Sottoinsieme di `Asset` che basta a un provider per risolvere una
    quotazione — mai l'intero modello ORM, per non legare l'interfaccia allo
    schema DB (stesso principio di `CategoryOption` in app/ai/base.py)."""

    id: uuid.UUID
    symbol: str | None
    isin: str | None
    name: str
    currency: str


@dataclass(frozen=True)
class Quote:
    price: Decimal
    currency: str
    as_of: date


class MarketDataProviderError(Exception):
    """Errore di comunicazione/configurazione col provider (rete, auth,
    simbolo non risolvibile dal servizio esterno). Mai lasciata propagare
    fino a rompere il job di refresh: il chiamante la cattura e passa
    all'asset successivo — un provider irraggiungibile non deve bloccare
    l'aggiornamento degli altri asset (stesso principio di AIProviderError)."""


class MarketDataProvider(Protocol):
    provider: str

    async def fetch_quote(self, asset: AssetRef) -> Quote | None:
        """Ritorna l'ultima quotazione disponibile o `None` se l'asset non e'
        risolvibile da questo provider (es. nessun `symbol` impostato, o il
        provider non lo trova) — non e' un errore, e' un dato assente
        gestito (DoD M09). Solleva `MarketDataProviderError` solo per
        problemi di comunicazione con un endpoint che dovrebbe rispondere."""
        ...

    async def test_connection(self) -> None:
        """Verifica raggiungibilita'/credenziali senza risolvere un asset
        specifico. Solleva `MarketDataProviderError` con un messaggio
        comprensibile in caso di problema; ritorna silenziosamente se la
        connessione funziona."""
        ...

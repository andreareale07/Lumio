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
from datetime import date, datetime
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


@dataclass(frozen=True)
class PricePoint:
    """`at` porta sempre l'istante completo, anche per i preset giornalieri
    (mezzanotte UTC in quel caso) — solo il chiamante che persiste in
    `asset_prices` (una riga per giorno) lo tronca a `.date()`. Troncarlo
    qui, nel provider, perderebbe l'informazione oraria che i preset
    intraday (1G/1S) mostrano nel grafico (bug reale osservato: senza,
    tutti i punti di un giorno intraday condividono la stessa etichetta)."""

    at: datetime
    price: Decimal


@dataclass(frozen=True)
class FxQuote:
    """Tasso di cambio corrente per una coppia (from_currency, to_currency)
    — mai una valuta sull'oggetto stesso (a differenza di `Quote`, dove
    l'asset la porta gia'): la coppia e' l'argomento della chiamata, non un
    dato risolto dal provider."""

    rate: Decimal
    as_of: date


@dataclass(frozen=True)
class AssetProfile:
    """Arricchimento best-effort (Step 3): ogni campo e' indipendentemente
    opzionale — un provider puo' avere l'emittente ma non l'AUM, o niente
    affatto. Mai un valore "N/A", solo `None` (il chiamante lo traduce in
    "riga non mostrata", MAI in errore o placeholder).

    `display_name`: nome "pulito" del titolo secondo il provider (es.
    "Apple Inc.", "D-Wave Quantum Inc."), MAI una sovrascrittura di
    `Asset.name` — quel campo resta cio' che il parser Trade Republic ha
    estratto dal PDF originale (spesso con suffissi di borsa tedeschi come
    "DL-,0001" = valore nominale in dollari, a volte perfino con refusi del
    broker, es. "QUATUM" invece di "Quantum"). Il chiamante decide se e
    dove mostrare questo nome al posto di quello grezzo — mai una modifica
    permanente al dato salvato dall'utente/dal parser."""

    issuer: str | None
    category: str | None
    aum: Decimal | None
    distribution_policy: str | None
    display_name: str | None = None


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

    async def fetch_history(self, asset: AssetRef, preset: str) -> list[PricePoint] | None:
        """Serie storica per il preset richiesto (vedi `HISTORY_PRESETS` in
        `app/api/v1/assets.py` per i preset validi), ordinata per data
        crescente. `None` = questo provider non supporta lo storico (non un
        errore: il chiamante lo mostra come "provider senza storico", mai
        come "nessun dato"). Solleva `MarketDataProviderError` solo per
        problemi di comunicazione con un endpoint che dovrebbe rispondere."""
        ...

    async def fetch_profile(self, asset: AssetRef) -> AssetProfile | None:
        """Arricchimento best-effort (emittente/categoria/AUM/accumulo-
        distribuzione). A differenza di `fetch_quote`/`fetch_history`, NON
        solleva mai `MarketDataProviderError`: qualunque problema (auth,
        campo assente, endpoint fragile) risulta in `None` — l'arricchimento
        e' un extra, mai un blocco della pagina asset (vedi piano Step 3).
        `None` = nessun dato ottenuto (provider senza supporto o fetch
        fallito); il chiamante decide se mostrare un profilo gia' in cache."""
        ...

    async def fetch_fx_rate(self, from_currency: str, to_currency: str) -> FxQuote | None:
        """Tasso di cambio corrente. `None` = provider senza supporto FX
        (non un errore: il chiamante ricade sull'ultimo tasso persistito, se
        esiste — vedi `app/services/fx_rate_service.py`). Nessuna riga
        inversa dedotta da chi chiama: un tasso EUR->USD non implica
        USD->EUR (non garantito 1/rate). Solleva `MarketDataProviderError`
        solo per problemi di comunicazione con un endpoint che dovrebbe
        rispondere."""
        ...

    async def fetch_fx_history(
        self, from_currency: str, to_currency: str, preset: str
    ) -> list[PricePoint] | None:
        """Storico del tasso di cambio per il preset richiesto (stessi
        preset di `fetch_history`). `None` = provider senza supporto FX.
        Solleva `MarketDataProviderError` solo per problemi di comunicazione
        con un endpoint che dovrebbe rispondere."""
        ...

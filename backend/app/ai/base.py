"""Interfaccia astratta del classificatore AI (SPEC §25: `AIClassifier`).

Stesso pattern di `BankParser` (app/parsers/base.py) e `StorageProvider`: un
`Protocol` strutturale, non una classe base da ereditare. Il chiamante
(worker import, `app/services/ai_classification.py`) lavora solo con questa
interfaccia — aggiungere un provider non tocca il dominio transazioni
(ROADMAP M07 DoD: "switch tra provider via configurazione, zero modifiche al
dominio").

Le categorie vengono passate al provider per `code` (non `name`): `code` e'
uno slug stabile (vedi `app/models/category.py`), la UI puo' rinominare una
categoria senza invalidare il matching della risposta AI. La risposta del
provider deve indicare il `code` scelto tra quelli offerti; un code non
riconosciuto equivale a "nessuna classificazione" (mai forzare una categoria
arbitraria, SPEC §86 "il DB e' source of truth", l'AI e' solo un
classificatore).
"""
import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CategoryOption:
    id: uuid.UUID
    code: str
    name: str
    # Rework prompt AI: gerarchia (per raggruppare per padre nel prompt),
    # kind (per il filtro segno/tipo — vedi app/services/ai_classification.py)
    # e hint opzionale (app/classification/taxonomy.py) per disambiguare le
    # categorie il cui solo nome non basta a un LLM.
    parent_code: str | None = None
    parent_name: str | None = None
    kind: str = "expense"
    hint: str | None = None


@dataclass(frozen=True)
class ClassifiableTransaction:
    description_raw: str
    description_normalized: str | None
    merchant: str | None
    amount: str
    currency: str
    direction: str
    # Rework prompt AI: il modello vede ora anche COSA la banca dice che sia
    # il movimento (utile per non riproporre l'inferenza gia' certa a monte
    # — vedi la guardia negativa in ai_classification_job.py, che comunque
    # impedisce a investimenti/trasferimenti/ecc. di arrivare fin qui),
    # QUANDO (una spesa ricorrente il giorno 1 del mese e' quasi sempre un
    # abbonamento/affitto) e CHI (la controparte di un bonifico, quando
    # nota, e' spesso un segnale piu' forte della sola descrizione).
    transaction_type: str = "expense"
    transaction_date: str | None = None
    counterparty_name: str | None = None


@dataclass(frozen=True)
class AIClassificationResult:
    category_id: uuid.UUID
    raw_confidence: float | None
    explanation: str | None


class AIProviderError(Exception):
    """Errore di comunicazione/configurazione col provider (rete, auth,
    risposta non interpretabile). Mai lasciata propagare fino a rompere un
    import: il chiamante la cattura e tratta la transazione come non
    classificata da AI (le regole restano l'unica classificazione, se
    presente)."""


class AIClassifier(Protocol):
    provider: str

    async def classify(
        self, transaction: ClassifiableTransaction, categories: list[CategoryOption]
    ) -> AIClassificationResult | None:
        """Ritorna la categoria scelta (con confidence dichiarata dal
        modello) o None se il modello non ha trovato un match sensato tra le
        `categories` offerte. Solleva `AIProviderError` per problemi di
        comunicazione — mai per "nessuna categoria adatta", che e' un
        risultato legittimo (None), non un errore."""
        ...

    async def test_connection(self) -> None:
        """Verifica raggiungibilita'/credenziali senza classificare nulla.
        Solleva `AIProviderError` con un messaggio comprensibile in caso di
        problema; ritorna silenziosamente se la connessione funziona."""
        ...

    async def list_models(self) -> list[str]:
        """Elenco dei modelli disponibili per la UI (menu a tendina invece
        di un campo di testo libero, dove il provider lo consente). Lista
        vuota, mai un errore silenzioso: un provider che non supporta la
        discovery (es. `custom` verso un server che non implementa
        `/models`) ritorna semplicemente `[]`, lasciando alla UI il fallback
        sul campo di testo libero. Solleva `AIProviderError` solo per un
        problema di comunicazione con un endpoint che *dovrebbe* supportarla
        (Ollama, OpenAI, Anthropic)."""
        ...

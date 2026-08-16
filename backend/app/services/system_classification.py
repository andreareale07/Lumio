"""Livello 2 della pipeline di classificazione (rework tassonomia/pipeline
post-M11.5): decide una categoria di sistema da `transaction_type` +
`description_raw` quando e' deducibile senza inferenza — gira DOPO le
regole utente (che vincono sempre, mai sovrascritte) e PRIMA dell'AI (che
vede solo cio' che resta). Stessa natura pura di `rules_engine.py`: nessuna
dipendenza da DB, unit-testabile in isolamento.

Bug reale che questo modulo risolve (riportato dall'utente): un piano di
accumulo (PAC) su ETF veniva mandato all'AI insieme a tutto il resto senza
categoria, e l'AI — potendo scegliere solo tra le poche categorie di spesa
esistenti — lo classificava come "Tempo libero" o "Abbonamenti". La riga era
gia' certa (transaction_type='investment' e/o descrizione riconosciuta da
`trade_parsing.parse_trade_description`): non andava mai chiesta a un
modello probabilistico.

Invariante non negoziabile per l'intera pipeline (vedi
`app/services/classification_pipeline.py`): una riga che risulta `None` qui
resta NON classificata a questo livello — non viene mai promossa
automaticamente a "indovinabile dall'AI" solo perche' questo livello non ha
trovato nulla. E' la guardia negativa nel job AI
(`app/worker/jobs/ai_classification_job.py`, basata su `transaction_type`,
non sull'esito di questa funzione) a impedire che un investimento/
trasferimento/dividendo/interesse/tassa/commissione arrivi comunque al
provider se la categoria di sistema attesa fosse stata disattivata
dall'utente.
"""
from dataclasses import dataclass

from app.classification.catalog import CATALOG
from app.classification.type_map import TRANSACTION_TYPE_TO_CATEGORY_CODE
from app.services.rules_engine import MatchableRow, matches
from app.services.trade_parsing import parse_trade_description

# transaction_type per cui questo livello (o la guardia negativa nel job AI)
# rende la riga ineleggibile per l'AI — indipendentemente dal fatto che
# `classify_by_transaction_type` trovi o meno una categoria specifica.
AI_EXCLUDED_TRANSACTION_TYPES = frozenset({"investment", "transfer", "dividend", "interest", "tax", "fee"})


def classify_by_transaction_type(transaction_type: str, description_raw: str) -> str | None:
    """Ritorna il `code` (non l'id: la risoluzione a category_id reale e'
    responsabilita' del chiamante DB-aware, vedi
    `app/services/classification_loader.py`) della categoria di sistema
    dedotta dal tipo di transazione, o `None` se `transaction_type` da solo
    non basta (expense/income/refund/adjustment: si prosegue verso il
    livello successivo, pattern di sistema o AI).
    """
    trade = parse_trade_description(description_raw)
    if transaction_type == "investment" or trade is not None:
        if trade is not None:
            if trade.source_type_raw == "Savings plan execution":
                return "investimenti.versamento_pac"
            if trade.type == "sell":
                return "investimenti.vendita_titoli"
            return "investimenti.acquisto_titoli"
        # transaction_type e' "investment" ma la descrizione non matcha
        # nessun formato noto (parser diverso da Trade Republic, o un
        # formato mai osservato prima): categoria generica di investimento,
        # mai un'ipotesi piu' specifica non supportata dal testo.
        return "investimenti.acquisto_titoli"
    return TRANSACTION_TYPE_TO_CATEGORY_CODE.get(transaction_type)


@dataclass(frozen=True)
class PatternMatch:
    category_code: str
    pattern_key: str  # per la spiegazione/diagnostica (Classification.explanation)


def classify_by_pattern(row: MatchableRow, *, disabled_keys: frozenset[str] = frozenset()) -> PatternMatch | None:
    """Livello 3: catalogo di pattern di sistema (merchant/keyword,
    `app/classification/catalog.py`), valutato DOPO il livello 2
    (transaction_type) e PRIMA dell'AI — risolve il bug reale riportato
    dall'utente sul carburante: prima che l'utente creasse a mano la
    categoria "Trasporti", l'AI non aveva alcuna categoria sensata tra cui
    scegliere per "ENI STAZIONE SERVIZIO". Un catalogo di pattern noti a
    priori copre i merchant piu' comuni senza aspettare che l'utente scopra
    ogni buco categoria per categoria.

    Ordinamento: priorita' crescente, poi ordine di dichiarazione nel
    catalogo (il catalogo e' una lista fissa nel codice, non serve un
    secondo criterio di tie-break come `created_at` per le regole utente).
    Nessuna interazione con le regole utente da gestire qui: questo livello
    gira SOLO se `classification_pipeline.classify_deterministic` non ha
    gia' trovato una regola utente che matcha, quindi una regola vince
    sempre per costruzione dell'ordine, non per un meccanismo di priorita'
    incrociata tra i due mondi.
    """
    candidates = sorted(
        (p for p in CATALOG if p.key not in disabled_keys),
        key=lambda p: p.priority,
    )
    for pattern in candidates:
        if matches(pattern.field, pattern.operator, pattern.value, row):
            return PatternMatch(category_code=pattern.category_code, pattern_key=pattern.key)
    return None


def is_ai_eligible(transaction_type: str) -> bool:
    """Guardia negativa: una riga con questo `transaction_type` non deve MAI
    arrivare al classificatore AI, anche se `classify_by_transaction_type`
    (o il livello 3, catalogo pattern) non hanno trovato nulla — es. la
    categoria attesa e' stata disattivata dall'utente. La riga resta
    semplicemente non classificata, non "ripiega" sull'AI."""
    return transaction_type not in AI_EXCLUDED_TRANSACTION_TYPES

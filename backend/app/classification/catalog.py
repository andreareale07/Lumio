"""Catalogo di pattern di sistema (merchant/keyword) — livello 3 della
pipeline di classificazione, gira DOPO le regole utente e il livello 2
(transaction_type) e PRIMA dell'AI. Risolve il bug reale riportato
dall'utente: il carburante veniva classificato correttamente solo DOPO che
l'utente aveva creato a mano la categoria "Trasporti" — l'AI non ha modo di
indovinare una categoria che non esiste nella tassonomia. Un catalogo di
pattern noti a priori copre i merchant italiani piu' comuni fin dal primo
giorno, senza aspettare che l'utente scopra il buco categoria per categoria.

Dato Python versionato nel codice (non una tabella DB): ogni merchant
aggiunto altrimenti richiederebbe una migration, rischierebbe di confondersi
con le `rules` dell'utente (che devono sempre vincere — vedi
`classification_pipeline.py`, questo livello gira dopo per costruzione
dell'ordine, nessun meccanismo di priorita' incrociata necessario), e non
sarebbe testabile in isolamento come `rules_engine.py`.

Override/disattivazione: l'utente crea una `Rule` normale che punta a
un'altra categoria — vince per costruzione, senza bisogno di alcun
meccanismo qui. Una futura UI per disattivare un singolo pattern (senza
crearne una regola) e' gia' prevista nel loader
(`app/services/classification_loader.py`, parametro `disabled_pattern_keys`,
oggi sempre vuoto) ma non implementata: rimandabile, l'override via regola
copre gia' il caso reale.

Regola anti-falso-positivo NON NEGOZIABILE, imposta da un test che itera
l'intero catalogo (`tests/test_catalog.py`): ogni pattern con `value` piu'
corto di 5 caratteri DEVE usare `operator="regex"` con `\\b...\\b` (parola
intera). Senza questo vincolo, `contains "IP"` matcherebbe "TRIPADVISOR",
`contains "COOP"` matcherebbe "COOPERATIVA EDILE" — un catalogo che genera
falsi positivi a valanga e' peggio di nessun catalogo.

`country` e' un metadato (raggruppamento futuro in UI), NON filtra in questa
versione: i merchant italiani reali non collidono con nulla, e i globali
(Netflix, Amazon) devono valere ovunque — filtrare per paese richiederebbe
una nozione di "paese del workspace" che oggi non esiste (un workspace puo'
avere conti di piu' paesi). Costruirlo ora sarebbe complessita' speculativa,
stessa posizione gia' presa in `trade_parsing.py`.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SystemPattern:
    key: str  # stabile, mai riusato: identita' per override/disattivazione futura
    field: str  # "merchant" | "description" (stessi campi di rules_engine)
    operator: str  # riusa gli operatori di rules_engine.matches
    value: str
    category_code: str
    priority: int = 100
    country: str | None = "IT"


CATALOG: list[SystemPattern] = [
    # --- Trasporti: carburante -----------------------------------------
    SystemPattern("fuel.eni", "description", "regex", r"\bENI\b", "trasporti.carburante"),
    SystemPattern("fuel.agip", "description", "regex", r"\bAGIP\b", "trasporti.carburante"),
    SystemPattern("fuel.q8", "description", "regex", r"\bQ8\b", "trasporti.carburante"),
    SystemPattern("fuel.ip", "description", "regex", r"\bIP\b", "trasporti.carburante"),
    SystemPattern("fuel.esso", "description", "regex", r"\bESSO\b", "trasporti.carburante"),
    SystemPattern("fuel.tamoil", "description", "contains", "TAMOIL", "trasporti.carburante"),
    SystemPattern("fuel.total_erg", "description", "contains", "TOTALERG", "trasporti.carburante"),
    SystemPattern("fuel.total_energies", "description", "contains", "TOTALENERGIES", "trasporti.carburante"),
    # --- Trasporti: pedaggi / parcheggi ----------------------------------
    SystemPattern("toll.telepass", "description", "contains", "TELEPASS", "trasporti.pedaggi"),
    SystemPattern("toll.autostrade", "description", "contains", "AUTOSTRADE PER", "trasporti.pedaggi"),
    # --- Alimentari: supermercato -----------------------------------------
    SystemPattern("grocery.lidl", "description", "regex", r"\bLIDL\b", "alimentari.supermercato"),
    SystemPattern("grocery.esselunga", "description", "contains", "ESSELUNGA", "alimentari.supermercato"),
    SystemPattern("grocery.conad", "description", "contains", "CONAD", "alimentari.supermercato"),
    SystemPattern("grocery.coop", "description", "regex", r"\bCOOP\b", "alimentari.supermercato"),
    SystemPattern("grocery.carrefour", "description", "contains", "CARREFOUR", "alimentari.supermercato"),
    SystemPattern("grocery.pam", "description", "regex", r"\bPAM\b", "alimentari.supermercato"),
    SystemPattern("grocery.eurospin", "description", "contains", "EUROSPIN", "alimentari.supermercato"),
    SystemPattern("grocery.md_discount", "description", "contains", "MD DISCOUNT", "alimentari.supermercato"),
    SystemPattern("grocery.penny", "description", "regex", r"\bPENNY\b", "alimentari.supermercato"),
    # --- Bar e ristoranti: delivery -----------------------------------
    SystemPattern("delivery.justeat", "description", "contains", "JUST EAT", "bar_ristoranti.delivery"),
    SystemPattern("delivery.glovo", "description", "contains", "GLOVO", "bar_ristoranti.delivery"),
    SystemPattern("delivery.deliveroo", "description", "contains", "DELIVEROO", "bar_ristoranti.delivery"),
    SystemPattern("delivery.uber_eats", "description", "contains", "UBER EATS", "bar_ristoranti.delivery"),
    # --- Salute: farmacia --------------------------------------------------
    SystemPattern("health.farmacia", "description", "contains", "FARMACIA", "salute.farmacia"),
    # --- Abbonamenti --------------------------------------------------------
    SystemPattern("subscription.netflix", "description", "contains", "NETFLIX", "abbonamenti.streaming"),
    SystemPattern("subscription.disney_plus", "description", "contains", "DISNEY PLUS", "abbonamenti.streaming"),
    SystemPattern("subscription.disney_plus_alt", "description", "contains", "DISNEY+", "abbonamenti.streaming"),
    SystemPattern("subscription.prime_video", "description", "contains", "PRIME VIDEO", "abbonamenti.streaming"),
    SystemPattern("subscription.spotify", "description", "contains", "SPOTIFY", "abbonamenti.streaming_musica"),
    SystemPattern("subscription.apple_music", "description", "contains", "APPLE MUSIC", "abbonamenti.streaming_musica"),
    SystemPattern("subscription.microsoft_365", "description", "contains", "MICROSOFT 365", "abbonamenti.software"),
    SystemPattern("subscription.office_365", "description", "contains", "OFFICE 365", "abbonamenti.software"),
    SystemPattern("subscription.google_one", "description", "contains", "GOOGLE ONE", "abbonamenti.cloud_storage"),
    SystemPattern("subscription.icloud", "description", "contains", "ICLOUD", "abbonamenti.cloud_storage"),
    SystemPattern("subscription.dropbox", "description", "contains", "DROPBOX", "abbonamenti.cloud_storage"),
    # Nessun pattern generico "Amazon" -> shopping.*: un acquisto Amazon puo'
    # essere qualunque cosa (libri, elettronica, casa, regali...) e la
    # tassonomia non ha un contenitore "marketplace" generico. Un pattern
    # deterministico qui produrrebbe piu' falsi positivi che valore — resta
    # deliberatamente all'AI, che ha almeno il contesto di importo/data.
]

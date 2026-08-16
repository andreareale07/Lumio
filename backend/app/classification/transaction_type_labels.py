"""Dizionario multilingua per il TIPO Trade Republic (colonna "tipo" del
PDF) -> chiave semantica canonica.

Nato da una domanda diretta dell'utente ("se in futuro usassi un estratto
conto in inglese funzionerebbe lo stesso?"): prima di questo modulo,
`TradeRepublicParser._transaction_type` riconosceva solo le etichette
italiane hardcoded — un utente con l'app Trade Republic impostata in
inglese (o un'altra lingua supportata) avrebbe visto ogni riga ricadere
nel fallback generico "indovina dal solo segno dell'importo", perdendo la
distinzione interessi/imposte/investimento/transazione con carta (lo
stesso bug categoria, spostato di un livello: dalla classificazione alla
determinazione del tipo).

Non esaustivo per design: aggiungere qui nuove varianti scoperte su dati
reali, mai indovinare una traduzione — un'etichetta non riconosciuta
ricade nel fallback onesto basato sulla sola direzione (vedi
`trade_republic.py:_transaction_type`), che e' un comportamento sicuro,
mai una mappatura sbagliata silenziosa.
"""

# Chiave semantica intermedia: la stessa etichetta "transazione con carta"
# dipende ANCHE dalla direzione (credit -> refund, debit -> expense), la
# risoluzione finale resta in _transaction_type — qui solo "quale
# etichetta semantica ha detto l'estratto conto", non ancora il
# transaction_type applicato.
SEMANTIC_KEYS = ("interest", "bonus", "tax", "trade", "card_transaction")

_LABEL_TO_SEMANTIC_KEY: dict[str, str] = {
    # Italiano (lingua storica di questo parser)
    "interessi": "interest",
    "premio": "bonus",
    "imposte": "tax",
    "commercio": "trade",
    "transazione con carta": "card_transaction",
    # English
    "interest": "interest",
    "bonus": "bonus",
    "tax": "tax",
    "taxes": "tax",
    "trade": "trade",
    "card transaction": "card_transaction",
    # Deutsch (Trade Republic e' un'azienda tedesca, l'app la offre di default)
    "zinsen": "interest",
    "prämie": "bonus",
    "steuern": "tax",
    "handel": "trade",
    "kartentransaktion": "card_transaction",
}


def classify_label(tipo: str) -> str | None:
    """Normalizza (spazi, maiuscole/minuscole) e cerca tra tutte le lingue
    note, restituendo la chiave semantica o `None` se non riconosciuta in
    nessuna — `None` e' il segnale che serve al chiamante per decidere il
    fallback, non un errore da correggere qui con un'ipotesi."""
    normalized = " ".join(tipo.strip().lower().split())
    return _LABEL_TO_SEMANTIC_KEY.get(normalized)

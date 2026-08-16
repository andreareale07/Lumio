"""Mappatura statica `transaction_type` -> `category code` di sistema.

Livello 2 della pipeline di classificazione (vedi
`app/services/system_classification.py`), casi DIRETTI: un `transaction_type`
che da solo basta a dedurre la categoria, senza bisogno di interpretare la
descrizione. Il caso "investment" NON e' qui apposta: scegliere tra
acquisto/vendita/PAC richiede `trade_parsing.parse_trade_description()`
sulla descrizione, quindi quella logica vive nel motore
(`system_classification.classify_by_transaction_type`), non in un
dizionario statico.

`expense`/`income`/`refund`/`adjustment` restano fuori da questa mappa di
proposito: sono troppo generici per dedurre una categoria dal solo tipo
("refund" e' la negazione di una spesa qualunque — la categoria giusta e'
quella della spesa originale, non "Rimborsi", altrimenti la spesa vera
sparirebbe dalle analytics). Quelle righe proseguono verso il livello
successivo (catalogo pattern / AI).
"""

TRANSACTION_TYPE_TO_CATEGORY_CODE: dict[str, str] = {
    "transfer": "trasferimenti.giroconto",
    "dividend": "entrate.dividendi",
    "interest": "entrate.interessi_attivi",
    "tax": "tasse",
    "fee": "commissioni",
}

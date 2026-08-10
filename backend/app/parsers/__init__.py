"""Registro dei parser bancari (SPEC §17, §94 — milestone 05).

Il sistema deve poter aggiungere nuove banche senza toccare il dominio
transazioni/import: questo modulo e' l'unico punto che conosce l'elenco
concreto dei parser disponibili. `bank_parsers` (DB) traccia quale
banca/versione e' stata usata per un import gia' fatto (audit/versionamento);
questo registro e' invece l'implementazione runtime effettiva, tenuta
separata perche' un `Protocol` non e' persistibile in una tabella.

Aggiungere un nuovo istituto significa: implementare `BankParser`, aggiungere
l'istanza a `PARSERS`, inserire la riga corrispondente in
`app/db/seed_data.py` (BANK_PARSERS) + relativa migration — nessuna modifica
a `app/api/v1/imports.py`, `app/worker/`, o ai modelli di dominio.
"""
from app.parsers.base import BankParser, ParsedStatement
from app.parsers.trade_republic import TradeRepublicParser

PARSERS: tuple[BankParser, ...] = (TradeRepublicParser(),)


def detect_parser(raw_bytes: bytes) -> BankParser | None:
    """Prova ogni parser registrato finche' uno riconosce il documento.

    Usata all'upload (SPEC §42: stage "banca riconosciuta"). Nessuna banca
    riconosciuta -> nessun parser -> l'upload viene rifiutato a monte.
    """
    for parser in PARSERS:
        if parser.detect(raw_bytes):
            return parser
    return None


def get_parser(parser_type: str) -> BankParser:
    """Risolve un parser dal suo `parser_type` (colonna `bank_parsers`).

    Usata dal worker, che conosce solo l'id di `bank_parsers` salvato
    sull'import al momento dell'upload — non ripete la detection.
    """
    for parser in PARSERS:
        if parser.parser_type == parser_type:
            return parser
    raise ValueError(f"nessun parser registrato per parser_type={parser_type!r}")


__all__ = ["BankParser", "ParsedStatement", "PARSERS", "detect_parser", "get_parser"]

"""Interfaccia astratta dei parser bancari (SPEC §17):

    class BankParser(Protocol):
        def detect(...)
        def parse(...)

Stesso pattern di `StorageProvider` (app/storage/base.py): un `Protocol`
strutturale, non una classe base da ereditare — chi consuma un `BankParser`
(il registro in `app/parsers/__init__.py`, l'endpoint di upload, il worker)
lavora solo con questa interfaccia, senza conoscere l'istituto concreto.

`ParsedStatement` riusa `ParsedRow` da `app.services.csv_import`: e' lo
stesso identico schema con cui il worker gia' crea le `Transaction` per il
canale CSV (milestone 04), cosi' i due canali di import (CSV, PDF) convergono
sulla stessa forma intermedia prima di toccare il dominio transazioni.
"""
from typing import Protocol

from app.services.csv_import import ParsedRow


class ParsedStatement:
    def __init__(self, rows: list[ParsedRow], warnings: list[str]) -> None:
        self.rows = rows
        self.warnings = warnings


class BankParser(Protocol):
    # Deve combaciare con `banks.code` (vedi app/db/seed_data.py) — collega
    # il parser alla banca durante la detection.
    bank_code: str
    # Chiave stabile salvata in `bank_parsers.parser_type`: usata dal worker
    # per risolvere di nuovo il parser concreto da un import gia' creato,
    # senza ripetere la detection (vedi app/parsers/__init__.py:get_parser).
    parser_type: str
    # SPEC §17: "Trade Republic -> parser v1, parser v2" — i formati PDF
    # possono cambiare. Incrementare quando cambia la logica di parse().
    version: str

    def detect(self, raw_bytes: bytes) -> bool:
        """True se `raw_bytes` e' (con ragionevole confidenza) un estratto
        conto di questa banca in questo formato. Non deve mai sollevare per
        un file non valido/corrotto: un `detect()` incerto ritorna False,
        lasciando che sia il chiamante a gestire "nessuna banca riconosciuta".
        """
        ...

    def parse(self, raw_bytes: bytes) -> ParsedStatement:
        """Estrae le transazioni. Puo' sollevare se il documento supera
        `detect()` ma poi risulta comunque non interpretabile (es. layout
        cambiato) — il chiamante (worker) tratta questo come fallimento
        dell'import, stesso comportamento di un CSV non parsabile."""
        ...

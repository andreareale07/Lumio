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
from dataclasses import dataclass
from typing import Protocol

from app.services.csv_import import ParsedRow


class ParsedStatement:
    def __init__(self, rows: list[ParsedRow], warnings: list[str]) -> None:
        self.rows = rows
        self.warnings = warnings


@dataclass
class TransferCounterparty:
    """Identita' della controparte di un movimento di bonifico, estratta
    dalla descrizione grezza — milestone 09.5b, SPEC §37 ("escludere
    correttamente i trasferimenti interni"). Entrambi opzionali: un parser
    puo' trovare solo il nome, solo l'IBAN, o nessuno dei due (in quel caso
    non estrae nulla, vedi `extract_transfer_counterparty`)."""

    name: str | None
    iban: str | None


@dataclass
class AccountHeaderInfo:
    """IBAN e nominativo del TITOLARE del conto (non di una controparte),
    estratti dall'intestazione del documento stesso — usati da
    `app/services/account_matching.py` per proporre a quale conto del
    workspace appartiene l'estratto conto appena caricato, invece di
    chiederlo sempre a mano. Entrambi opzionali per lo stesso motivo di
    `TransferCounterparty`: un parser puo' trovare solo uno dei due."""

    iban: str | None
    holder_name: str | None


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

    def default_transaction_type(self, source_type_raw: str, direction: str) -> str:
        """Mappatura HARDCODED (non configurabile) di questo parser da
        `source_type_raw` a `transaction_type` canonico — milestone 09.5:
        e' il fallback quando l'utente non ha salvato nessun override per
        questa etichetta (`app/services/transaction_type_mapping_service.py`),
        e il punto di confronto per capire se una transazione gia' importata
        e' ancora al default o e' stata corretta a mano. Stessa regola di
        design di sempre: mai assumere `transfer` da un'etichetta che non lo
        afferma esplicitamente (vedi `trade_republic.py:_transaction_type`)."""
        ...

    def extract_transfer_counterparty(self, description_raw: str) -> TransferCounterparty | None:
        """Milestone 09.5b: se `description_raw` e' un movimento di
        bonifico in un formato che questo parser sa interpretare, estrae
        nome/IBAN della controparte — usati da
        `app/services/transfer_recognition.py` per riconoscere se il
        bonifico e' verso un conto proprio del workspace (SPEC §37).
        `None` se la riga non e' un bonifico riconoscibile, O se questo
        parser non supporta l'estrazione: e' una capability OPZIONALE,
        specifica del formato reale di ogni istituto — un parser futuro
        (es. BancoPosta) puo' legittimamente non implementarla e ritornare
        sempre `None`, se il suo estratto conto non riporta questa
        informazione."""
        ...

    def extract_account_info(self, raw_bytes: bytes) -> AccountHeaderInfo | None:
        """IBAN/nominativo del titolare del conto, se l'intestazione del
        documento li riporta in un formato che questo parser sa
        interpretare. `None` se non trovati, O se questo parser non
        supporta l'estrazione — capability OPZIONALE, stesso principio di
        `extract_transfer_counterparty`: un parser che non la implementa
        degrada al fallback di selezione manuale del conto, mai un errore
        ne' un dato indovinato."""
        ...

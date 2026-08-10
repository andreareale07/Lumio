"""Parser CSV puro (nessuna dipendenza da DB/FastAPI, unit-testabile in
isolamento) per la milestone 04 — Import Engine.

`MappingConfig` e' lo schema di cio' che finisce in `import_mappings.config`
(JSONB): sia la mappatura colonna->campo transazione, sia i parametri di
parsing necessari per interpretare davvero un CSV bancario reale (che quasi
mai e' RFC4180 "puro": delimitatore `;`, decimale con virgola, importo
diviso in due colonne Dare/Avere, righe di intestazione da saltare, ecc.).

`detect_mapping` produce una proposta iniziale quando non esiste ancora
nessuna mappatura salvata (decisione presa con l'utente: mappature salvabili
complete, non un formato fisso ne' sola euristica — l'euristica serve solo a
non partire da un form vuoto).
"""
import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AmountMode = Literal["single_signed", "single_absolute_with_direction", "separate_debit_credit"]

# Formati data comuni negli export bancari IT/EN, in ordine di preferenza.
_CANDIDATE_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y")

_DATE_NAMES = ("data", "data operazione", "data contabile", "date", "transaction date", "booking date")
_VALUE_DATE_NAMES = ("data valuta", "value date", "valuta")
_DESCRIPTION_NAMES = ("descrizione", "description", "causale", "dettagli", "narrative", "operazione")
_AMOUNT_NAMES = ("importo", "amount", "importo operazione")
_DEBIT_NAMES = ("dare", "debit", "uscite", "addebito", "debit amount")
_CREDIT_NAMES = ("avere", "credit", "entrate", "accredito", "credit amount")
_DIRECTION_NAMES = ("tipo", "dare/avere", "direction", "segno")
_CURRENCY_NAMES = ("valuta importo", "currency", "divisa")
_REFERENCE_NAMES = ("riferimento", "reference", "causale abi", "id operazione")
_BALANCE_NAMES = ("saldo", "saldo contabile", "balance")

_DEFAULT_DEBIT_MARKERS = ("dare", "debit", "d", "-", "addebito")


class ColumnsConfig(BaseModel):
    transaction_date: str
    value_date: str | None = None
    description_raw: str
    amount: str | None = None
    amount_debit: str | None = None
    amount_credit: str | None = None
    direction: str | None = None
    currency: str | None = None
    reference: str | None = None
    balance_after: str | None = None


class MappingConfig(BaseModel):
    delimiter: str = ","
    encoding: str = "utf-8"
    decimal_separator: str = "."
    thousands_separator: str | None = None
    date_format: str = "%Y-%m-%d"
    skip_rows: int = Field(default=0, ge=0)
    default_currency: str = Field(default="EUR", min_length=3, max_length=3)
    amount_mode: AmountMode = "single_signed"
    # Solo per amount_mode="single_absolute_with_direction": valori (case
    # insensitive) della colonna `columns.direction` che indicano un
    # addebito; qualunque altro valore e' trattato come accredito.
    debit_markers: tuple[str, ...] = _DEFAULT_DEBIT_MARKERS
    columns: ColumnsConfig

    @field_validator("delimiter")
    @classmethod
    def _delimiter_single_char(cls, v: str) -> str:
        if len(v) != 1:
            raise ValueError("delimiter must be a single character")
        return v

    @model_validator(mode="after")
    def _amount_columns_consistent_with_mode(self) -> "MappingConfig":
        c = self.columns
        if self.amount_mode == "separate_debit_credit":
            if not c.amount_debit or not c.amount_credit:
                raise ValueError(
                    "separate_debit_credit richiede columns.amount_debit e columns.amount_credit"
                )
        else:
            if not c.amount:
                raise ValueError(f"{self.amount_mode} richiede columns.amount")
            if self.amount_mode == "single_absolute_with_direction" and not c.direction:
                raise ValueError("single_absolute_with_direction richiede columns.direction")
        return self


class ParsedRow(BaseModel):
    transaction_date: date
    value_date: date | None
    description_raw: str
    description_normalized: str
    amount: Decimal
    currency: str
    direction: str
    transaction_type: str
    reference: str | None
    balance_after: Decimal | None


def _normalize_amount(raw: str, config: MappingConfig) -> Decimal:
    value = raw.strip()
    if config.thousands_separator:
        value = value.replace(config.thousands_separator, "")
    if config.decimal_separator != ".":
        value = value.replace(config.decimal_separator, ".")
    # Alcuni export usano parentesi per i negativi, es. "(12,50)".
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1]
    value = value.replace(" ", "")
    amount = Decimal(value)
    return -amount if negative else amount


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_rows(text: str, config: MappingConfig) -> tuple[list[ParsedRow], list[str]]:
    """Ritorna (righe valide, warning). I warning contengono solo numero
    riga e motivo — mai il contenuto della riga (SPEC §55: nessun dato
    finanziario nei log/messaggi diagnostici).
    """
    lines = text.splitlines()[config.skip_rows :]
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=config.delimiter)

    rows: list[ParsedRow] = []
    warnings: list[str] = []
    c = config.columns

    for line_number, raw_row in enumerate(reader, start=config.skip_rows + 2):
        try:
            transaction_date = datetime.strptime(
                raw_row[c.transaction_date].strip(), config.date_format
            ).date()
        except (KeyError, ValueError):
            warnings.append(f"riga {line_number}: data non valida o colonna mancante")
            continue

        value_date: date | None = None
        if c.value_date and raw_row.get(c.value_date, "").strip():
            try:
                value_date = datetime.strptime(raw_row[c.value_date].strip(), config.date_format).date()
            except ValueError:
                value_date = None  # non bloccante: e' un campo accessorio

        description_raw = raw_row.get(c.description_raw, "")
        if not description_raw or not description_raw.strip():
            warnings.append(f"riga {line_number}: descrizione mancante")
            continue

        try:
            amount, direction = _resolve_amount_and_direction(raw_row, config)
        except (InvalidOperation, KeyError, ValueError):
            warnings.append(f"riga {line_number}: importo non valido o colonna mancante")
            continue

        currency = config.default_currency
        if c.currency and raw_row.get(c.currency, "").strip():
            currency = raw_row[c.currency].strip().upper()

        balance_after: Decimal | None = None
        if c.balance_after and raw_row.get(c.balance_after, "").strip():
            try:
                balance_after = _normalize_amount(raw_row[c.balance_after], config)
            except InvalidOperation:
                balance_after = None

        reference = raw_row.get(c.reference, "").strip() if c.reference else None

        rows.append(
            ParsedRow(
                transaction_date=transaction_date,
                value_date=value_date,
                # description_raw non viene mai alterato (regola non
                # negoziabile) — solo la versione normalizzata collassa gli
                # spazi, per la ricerca/visualizzazione.
                description_raw=description_raw,
                description_normalized=_collapse_whitespace(description_raw),
                amount=amount,
                currency=currency,
                direction=direction,
                # Nessun rules engine ne' AI ancora disponibili (arrivano in
                # M06/M07): default onesto e correggibile dall'utente.
                transaction_type="expense" if direction == "debit" else "income",
                reference=reference or None,
                balance_after=balance_after,
            )
        )

    return rows, warnings


def _resolve_amount_and_direction(raw_row: dict, config: MappingConfig) -> tuple[Decimal, str]:
    c = config.columns
    if config.amount_mode == "separate_debit_credit":
        debit_raw = raw_row.get(c.amount_debit, "").strip()
        credit_raw = raw_row.get(c.amount_credit, "").strip()
        if debit_raw:
            amount = _normalize_amount(debit_raw, config)
            return -abs(amount), "debit"
        if credit_raw:
            amount = _normalize_amount(credit_raw, config)
            return abs(amount), "credit"
        raise ValueError("ne' dare ne' avere valorizzati")

    if config.amount_mode == "single_absolute_with_direction":
        amount = abs(_normalize_amount(raw_row[c.amount], config))
        marker = raw_row.get(c.direction, "").strip().lower()
        is_debit = marker in config.debit_markers
        return (-amount, "debit") if is_debit else (amount, "credit")

    # single_signed: il segno del valore stesso decide la direzione.
    amount = _normalize_amount(raw_row[c.amount], config)
    return amount, "debit" if amount < 0 else "credit"


def detect_mapping(sample_text: str) -> MappingConfig:
    """Euristica di proposta iniziale quando non esiste ancora nessuna
    mappatura salvata per il conto. Non deve essere perfetta: l'utente la
    conferma o corregge prima di avviare l'import vero (nessun job viene
    accodato solo sulla base di questa proposta).
    """
    delimiter = _sniff_delimiter(sample_text)
    header_index = 0
    reader = csv.reader(io.StringIO(sample_text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        raise ValueError("file vuoto o non riconoscibile come CSV")
    header = [h.strip() for h in rows[header_index]]
    sample_rows = rows[header_index + 1 : header_index + 6]

    def _find(names: tuple[str, ...]) -> str | None:
        lowered = {h.lower(): h for h in header}
        for name in names:
            if name in lowered:
                return lowered[name]
        return None

    date_col = _find(_DATE_NAMES) or (header[0] if header else None)
    description_col = _find(_DESCRIPTION_NAMES) or (header[1] if len(header) > 1 else header[0])
    debit_col = _find(_DEBIT_NAMES)
    credit_col = _find(_CREDIT_NAMES)
    amount_col = _find(_AMOUNT_NAMES)
    direction_col = _find(_DIRECTION_NAMES)

    if debit_col and credit_col:
        amount_mode: AmountMode = "separate_debit_credit"
    elif amount_col and direction_col:
        amount_mode = "single_absolute_with_direction"
    else:
        amount_mode = "single_signed"
        amount_col = amount_col or _find(_DEBIT_NAMES) or (header[-1] if header else None)

    columns = ColumnsConfig(
        transaction_date=date_col,
        value_date=_find(_VALUE_DATE_NAMES),
        description_raw=description_col,
        amount=amount_col if amount_mode != "separate_debit_credit" else None,
        amount_debit=debit_col if amount_mode == "separate_debit_credit" else None,
        amount_credit=credit_col if amount_mode == "separate_debit_credit" else None,
        direction=direction_col if amount_mode == "single_absolute_with_direction" else None,
        currency=_find(_CURRENCY_NAMES),
        reference=_find(_REFERENCE_NAMES),
        balance_after=_find(_BALANCE_NAMES),
    )

    amount_sample_col = amount_col or debit_col
    decimal_separator, thousands_separator = _sniff_decimal_style(
        [row[header.index(amount_sample_col)] for row in sample_rows if amount_sample_col in header]
        if amount_sample_col in header
        else []
    )
    date_format = _sniff_date_format(
        [row[header.index(date_col)] for row in sample_rows if date_col in header]
        if date_col in header
        else []
    )

    return MappingConfig(
        delimiter=delimiter,
        decimal_separator=decimal_separator,
        thousands_separator=thousands_separator,
        date_format=date_format,
        skip_rows=0,
        amount_mode=amount_mode,
        columns=columns,
    )


def _sniff_delimiter(sample_text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample_text[:4096], delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _sniff_decimal_style(sample_values: list[str]) -> tuple[str, str | None]:
    for value in sample_values:
        value = value.strip()
        if not value:
            continue
        has_comma = "," in value
        has_dot = "." in value
        if has_comma and has_dot:
            # L'ultimo separatore incontrato e' quasi sempre il decimale:
            # "1.234,56" (IT) vs "1,234.56" (US).
            if value.rfind(",") > value.rfind("."):
                return ",", "."
            return ".", ","
        if has_comma:
            return ",", None
        if has_dot:
            return ".", None
    return ".", None


def _sniff_date_format(sample_values: list[str]) -> str:
    candidates = [v.strip() for v in sample_values if v.strip()]
    if not candidates:
        return "%Y-%m-%d"
    for fmt in _CANDIDATE_DATE_FORMATS:
        if all(_matches_date_format(v, fmt) for v in candidates):
            return fmt
    return "%Y-%m-%d"


def _matches_date_format(value: str, fmt: str) -> bool:
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False

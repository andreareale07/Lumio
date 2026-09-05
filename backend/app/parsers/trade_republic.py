"""Parser PDF per gli estratti conto di Trade Republic (milestone 05, primo
parser di riferimento — SPEC §94).

L'estratto conto e' un PDF renderizzato da un template (nessuna riga di
tabella disegnata: `page.extract_tables()` di pdfplumber non trova nulla e
`extract_text()` mescola l'ordine di lettura quando una cella va a capo).
La strategia usata qui, verificata sull'estratto conto reale allegato dalla
milestone (147 transazioni, nessuna discrepanza — vedi sotto):

1. `page.extract_words()` da' ogni parola con le sue coordinate (top, x0).
2. Le parole si raggruppano in "righe visive" per vicinanza verticale
   (`_ROW_GAP_POINTS`): lo scarto tra righe della STESSA transazione e'
   sempre ~3-5pt (perche' la colonna DATA va sempre a capo su due righe,
   "01 mag" / "2026", allungando la riga anche quando TIPO/DESCRIZIONE
   stanno su una riga sola), lo scarto tra transazioni DIVERSE e' sempre
   piu' di 20pt. Questo raggruppamento vale su qualunque pagina, comprese
   intestazione/riepilogo/note finali: quelle righe non vengono scartate qui,
   ma piu' avanti, perche' non producono mai una DATA valida.
3. Le parole di ogni riga visiva si assegnano a una colonna (DATA/TIPO/
   DESCRIZIONE) in base a x0 (le soglie sono quelle del template, verificate
   sull'header "DATA TIPO DESCRIZIONE..." presente su ogni pagina).
4. Gli importi (IN ENTRATA / IN USCITA / SALDO) NON si assegnano per x0: per
   importi a 3 cifre pdfplumber a volte incolla il simbolo "€" di fine
   colonna al numero della colonna successiva in un unico token (es.
   "€6.266,14"), che ricadrebbe nella colonna sbagliata. Si cercano invece
   tutti i token con una coda numerica in stile IT (`_AMOUNT_TAIL_RE`) a
   destra della soglia x0=400 (oltre DESCRIZIONE), ordinati da sinistra a
   destra: l'ULTIMO e' sempre il SALDO (colonna piu' a destra), l'eventuale
   token prima di esso e' l'importo IN ENTRATA o IN USCITA a seconda che la
   sua x0 sia prima o dopo la soglia tra le due colonne (x0=450).
5. Una riga visiva e' una transazione solo se la colonna DATA, cosi'
   ricostruita, interpreta come "DD mmm YYYY" (mese abbreviato IT) — questo
   e', non un range di coordinate verticali, e' cio' che esclude
   automaticamente intestazione di pagina, riepilogo saldi, tabella
   "PANORAMICA DEL SALDO" dell'ultima pagina e note legali, senza bisogno di
   conoscere dove finisce la tabella.

Validazione empirica (script una tantum, non nel repo): sul PDF reale di
riferimento, la somma dei 147 importi IN ENTRATA riconosciuti e la somma dei
147 IN USCITA coincidono esattamente con "SALDO INIZIALE ... SALDO FINALE"
del riepilogo di pagina 1, e ricalcolando il saldo progressivo riga per riga
si ottiene, per tutte le 147 righe con un SALDO stampato, lo stesso valore
mostrato nel PDF — nessuna discrepanza.
"""
import io
import re
from datetime import date
from decimal import Decimal

import pdfplumber

from app.classification.transaction_type_labels import classify_label
from app.parsers.base import AccountHeaderInfo, ParsedStatement, TransferCounterparty
from app.services.csv_import import ParsedRow

_ITALIAN_MONTHS = {
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
}
_DATE_RE = re.compile(r"^(\d{2})\s+([a-z]{3})\s+(\d{4})$")
_AMOUNT_TAIL_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})$")
_WHITESPACE_RE = re.compile(r"\s+")

# Milestone 09.5b: formato verificato su un estratto conto reale (SPEC §37) —
# la colonna DESCRIZIONE dei bonifici riporta nome e IBAN della controparte,
# stessa struttura sia in entrata che in uscita, solo il verbo cambia:
# "Outgoing transfer for {nome} ({iban})" / "Incoming transfer for {nome} ({iban})".
_TRANSFER_COUNTERPARTY_RE = re.compile(
    r"^(?:Outgoing|Incoming) transfer for (?P<name>.+?) \((?P<iban>[A-Z]{2}\d{2}[A-Z0-9]+)\)$"
)

# Soglie in punti PDF, specifiche di questo template (SPEC §17: se Trade
# Republic cambia layout, serve una nuova versione del parser, non un
# aggiustamento qui — vedi `version` sotto).
_ROW_GAP_POINTS = 9.0
_COL_DATA = (60.0, 100.0)
_COL_TIPO = (100.0, 150.0)
_COL_DESCRIZIONE = (150.0, 410.0)
_COL_AMOUNT_MIN_X0 = 400.0
_COL_ENTRATA_USCITA_SPLIT_X0 = 450.0

_DETECT_MARKERS = ("TRADE REPUBLIC", "TRBKITMMXXX")


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _parse_amount(raw: str) -> Decimal:
    return Decimal(raw.replace(".", "").replace(",", "."))


def _bucket_for_x0(x0: float) -> str | None:
    if _COL_DATA[0] <= x0 < _COL_DATA[1]:
        return "data"
    if _COL_TIPO[0] <= x0 < _COL_TIPO[1]:
        return "tipo"
    if _COL_DESCRIZIONE[0] <= x0 < _COL_DESCRIZIONE[1]:
        return "descrizione"
    return None


def _cluster_into_rows(words: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    current: list[dict] = []
    prev_top: float | None = None
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if prev_top is not None and (word["top"] - prev_top) > _ROW_GAP_POINTS:
            rows.append(current)
            current = []
        current.append(word)
        prev_top = word["top"]
    if current:
        rows.append(current)
    return rows


def _join_bucket(words: list[dict]) -> str:
    return " ".join(w["text"] for w in sorted(words, key=lambda w: (w["top"], w["x0"])))


def _extract_amounts(row_words: list[dict]) -> tuple[Decimal | None, Decimal | None, Decimal | None, str | None]:
    """Ritorna (entrata, uscita, saldo, warning). Vedi il modulo docstring
    per il perche' non si usa un semplice bucket per x0 qui."""
    tokens: list[tuple[float, Decimal]] = []
    for w in row_words:
        if w["x0"] < _COL_AMOUNT_MIN_X0:
            continue
        match = _AMOUNT_TAIL_RE.search(w["text"])
        if match:
            tokens.append((w["x0"], _parse_amount(match.group(1))))
    tokens.sort(key=lambda t: t[0])

    if len(tokens) == 2:
        (x0, first_value), (_, saldo) = tokens
        if x0 < _COL_ENTRATA_USCITA_SPLIT_X0:
            return first_value, None, saldo, None
        return None, first_value, saldo, None
    if len(tokens) == 1:
        x0, value = tokens[0]
        if x0 < _COL_ENTRATA_USCITA_SPLIT_X0:
            return value, None, None, "riga con importo ma senza saldo leggibile"
        return None, value, None, "riga con importo ma senza saldo leggibile"
    return None, None, None, "riga con data valida ma nessun importo riconosciuto"


def _transaction_type(tipo: str, direction: str) -> str:
    """Mappa il TIPO Trade Republic sull'enum esistente di `transactions`
    (nessuna colonna dedicata per buy/sell/dividendo: quel dettaglio arriva
    con il dominio Portfolio, M09 — qui ogni movimento "Commercio" e' un
    generico `investment`, coerente con SPEC §32-38 non ancora implementate).
    Decisione presa come dettaglio minore (non specificato da SPEC/ROADMAP
    per M05): mappatura onesta e corregibile dall'utente, stesso principio
    gia' usato dal parser CSV per il default expense/income.

    Regola di design (hotfix pre-M09, vedi git blame/ROADMAP): un parser puo'
    mappare solo cio' che l'etichetta *afferma*, non cio' che deduce. Se
    l'etichetta e' semantica ("Interessi", "Imposte") si mappa sul tipo
    canonico corrispondente. Se l'etichetta e' solo uno STRUMENTO di
    pagamento ("Bonifico") non si deduce nulla oltre al segno: un bonifico
    puo' essere un incasso da un cliente (income), un pagamento a un
    fornitore (expense) o un trasferimento tra due conti propri (transfer) —
    l'estratto conto di UN SOLO conto non permette di distinguere questi tre
    casi. Prima di questo fix "Bonifico" mappava sempre su `transfer`, che e'
    escluso dal cash flow (`analytics.py:_EXCLUDED_FROM_CASH_FLOW`): ogni
    bonifico in entrata o in uscita spariva silenziosamente da entrate/spese
    (bug osservato su dati reali). `transfer` resta assegnabile solo
    manualmente dall'utente via UI/API, mai da un parser (SPEC §21, pairing
    tra le due transazioni gemelle rimandato).

    Il riconoscimento dell'etichetta semantica passa da
    `app.classification.transaction_type_labels.classify_label`, che copre
    piu' lingue (italiano/inglese/tedesco) — l'app Trade Republic dell'utente
    potrebbe non essere in italiano, e prima di questo modulo ogni etichetta
    non italiana ricadeva silenziosamente nel fallback direzione-soltanto.
    """
    semantic_key = classify_label(tipo)
    if semantic_key == "interest":
        return "interest"
    if semantic_key == "bonus":
        return "income"
    if semantic_key == "tax":
        return "tax"
    if semantic_key == "trade":
        return "investment"
    if semantic_key == "card_transaction":
        return "refund" if direction == "credit" else "expense"
    # "bonifico"/"transfer"/"überweisung" e qualunque TIPO non riconosciuto
    # in nessuna lingua nota: fallback onesto sulla sola direzione, stesso
    # principio del parser CSV.
    return "income" if direction == "credit" else "expense"


class TradeRepublicParser:
    bank_code = "trade_republic"
    parser_type = "trade_republic_pdf"
    version = "1"

    def default_transaction_type(self, source_type_raw: str, direction: str) -> str:
        """Punto di accesso stabile al default hardcoded di questo parser
        (milestone 09.5: serve sia all'import — se non esiste un override
        dell'utente — sia al ricalcolo in `transaction_type_mapping_service.
        reapply_mapping`, per capire se una transazione e' ancora al valore
        di default o e' stata corretta a mano). Nessun comportamento nuovo,
        solo un metodo del `BankParser` che espone `_transaction_type`."""
        return _transaction_type(source_type_raw, direction)

    def extract_transfer_counterparty(self, description_raw: str) -> TransferCounterparty | None:
        """Milestone 09.5b: `None` se la descrizione non e' nel formato
        "Outgoing/Incoming transfer for {nome} ({iban})" verificato sui
        dati reali — mai un'estrazione parziale o indovinata."""
        match = _TRANSFER_COUNTERPARTY_RE.match(description_raw.strip())
        if match is None:
            return None
        return TransferCounterparty(name=match.group("name"), iban=match.group("iban"))

    def extract_account_info(self, raw_bytes: bytes) -> AccountHeaderInfo | None:
        """Sempre `None` per ora: il formato dell'intestazione Trade
        Republic su IBAN personale/nominativo del titolare NON e' stato
        ancora verificato su un estratto conto reale (a differenza di
        `_TRANSFER_COUNTERPARTY_RE` sopra, verificato su dati reali in
        M09.5b). L'unico IBAN oggi noto nell'header (vedi `_DETECT_MARKERS`)
        e' quello della FILIALE della banca, non del titolare — usarlo
        produrrebbe un match falso su ogni singolo estratto Trade Republic
        di qualunque utente. Da implementare con un regex dedicato solo
        dopo aver confermato formato/etichetta su un PDF reale; nel
        frattempo il comportamento e' identico a un parser che non supporta
        questa capability (fallback: selezione manuale del conto)."""
        return None

    def detect(self, raw_bytes: bytes) -> bool:
        try:
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                if not pdf.pages:
                    return False
                text = pdf.pages[0].extract_text() or ""
        except Exception:
            return False
        return all(marker in text for marker in _DETECT_MARKERS)

    def parse(self, raw_bytes: bytes) -> ParsedStatement:
        rows: list[ParsedRow] = []
        warnings: list[str] = []

        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
                for row_words in _cluster_into_rows(words):
                    buckets: dict[str, list[dict]] = {}
                    for word in row_words:
                        bucket = _bucket_for_x0(word["x0"])
                        if bucket is not None:
                            buckets.setdefault(bucket, []).append(word)

                    data_text = _join_bucket(buckets.get("data", []))
                    match = _DATE_RE.match(data_text.lower())
                    if not match:
                        continue  # non e' una riga di transazione (SPEC: vedi docstring modulo)
                    day, month_abbr, year = match.groups()
                    if month_abbr not in _ITALIAN_MONTHS:
                        continue
                    transaction_date = date(int(year), _ITALIAN_MONTHS[month_abbr], int(day))

                    tipo = _join_bucket(buckets.get("tipo", []))
                    description_raw = _join_bucket(buckets.get("descrizione", []))
                    if not description_raw:
                        warnings.append(f"pagina {page_number}: riga del {data_text} senza descrizione, saltata")
                        continue

                    entrata, uscita, saldo, amount_warning = _extract_amounts(row_words)
                    if amount_warning is not None and entrata is None and uscita is None:
                        warnings.append(f"pagina {page_number}: {amount_warning} ({data_text})")
                        continue
                    if amount_warning is not None:
                        warnings.append(f"pagina {page_number}: {amount_warning} ({data_text})")

                    amount = entrata if entrata is not None else uscita
                    if amount is None:
                        continue
                    direction = "credit" if entrata is not None else "debit"
                    transaction_type = _transaction_type(tipo, direction)

                    rows.append(
                        ParsedRow(
                            transaction_date=transaction_date,
                            value_date=None,
                            description_raw=description_raw,
                            description_normalized=_collapse_whitespace(description_raw),
                            amount=amount if direction == "credit" else -amount,
                            currency="EUR",
                            direction=direction,
                            transaction_type=transaction_type,
                            source_type_raw=tipo or None,
                            reference=None,
                            balance_after=saldo,
                        )
                    )

        if not rows:
            warnings.append("nessuna transazione riconosciuta nel documento")
        return ParsedStatement(rows=rows, warnings=warnings)

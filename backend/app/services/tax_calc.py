"""Motore fiscale PURO (SPEC_TAX_REGIME.md FETTA 1) — nessuna dipendenza da
DB/FastAPI, stessa separazione di `position_calc.py` per le posizioni.
`build_loss_pocket` deriva lo zainetto fiscale (redditi_diversi non ancora
scaduti/compensati) da una lista di `LossPocketEntry`. In FETTA 1 la lista
viene SOLO dai saldi di apertura manuali (`tax_opening_service.py`); in
FETTA 2 sara' `aperture + eventi realizzativi dal motore a lotti`, senza
modificare questa funzione — l'unico cambiamento sara' chi costruisce la
lista di entry, non come viene aggregata.

`formed_under_ruleset_code` arriva GIA' risolto dal chiamante (timbro di
audit scritto dal server al momento della creazione dell'apertura,
risolvendo `formation_date` — mai dal client, mai ricalcolato qui): questa
funzione applica solo la conversione del ruleset CONSUMANTE (quello vigente
a `on`), mai riscrivendo lo storico di formazione.

Unica eccezione futura (FETTA 2, non costruire ora): la chiusura d'anno
(`tax_year_closures`) congelera' il numero dichiarato una volta presentato
il quadro RT — questa funzione non deve mai congelare nulla da sola.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.tax.base import TaxRuleset, quantize_money


@dataclass(frozen=True)
class LossPocketEntry:
    formation_date: date
    nominal: Decimal
    income_category: str
    perimeter: str  # codice regime (per_account: id conto; aggregate: "dichiarativo")
    source: str  # "user_opening" in FETTA 1 — FETTA 2 aggiungera' altri valori
    formed_under_ruleset_code: str
    # None per le aperture manuali (un saldo aggregato, non legato a un
    # titolo specifico) — valorizzato per le righe "computed" (FETTA 2):
    # senza questo l'utente non puo' capire QUALE vendita ha generato la
    # minusvalenza (bug di chiarezza segnalato dall'utente in QA).
    asset_id: uuid.UUID | None = None


@dataclass(frozen=True)
class LossPocketRow:
    formation_date: date
    nominal: Decimal
    income_category: str
    perimeter: str
    source: str
    formed_under_ruleset_code: str
    applied_ruleset_code: str
    coefficient: Decimal
    usable_amount: Decimal
    conversion_reference: str | None
    expires_on: date
    is_expired: bool
    asset_id: uuid.UUID | None = None


@dataclass(frozen=True)
class LossPocketResult:
    rows: tuple[LossPocketRow, ...]
    totals_by_perimeter: dict[str, Decimal]


def build_loss_pocket(entries: list[LossPocketEntry], ruleset: TaxRuleset, on: date) -> LossPocketResult:
    rows: list[LossPocketRow] = []
    # Ordine FIFO per anno di formazione, PER PERIMETRO — e' l'ordine in cui
    # ciascuna voce verrebbe consumata da una compensazione futura (FETTA 2);
    # qui e' solo l'ordine di presentazione, nessuna riduzione di importo
    # avviene: il nominale non viene mai mutato.
    for entry in sorted(entries, key=lambda e: (e.perimeter, e.formation_date)):
        conversion = ruleset.conversion_for(entry.formation_date)
        coefficient = conversion.coefficient if conversion is not None else Decimal("1")
        usable_amount = quantize_money(entry.nominal * coefficient)
        expires_on = date(entry.formation_date.year + ruleset.carry_forward.years, 12, 31)
        rows.append(
            LossPocketRow(
                formation_date=entry.formation_date,
                nominal=entry.nominal,
                income_category=entry.income_category,
                perimeter=entry.perimeter,
                source=entry.source,
                formed_under_ruleset_code=entry.formed_under_ruleset_code,
                applied_ruleset_code=ruleset.code,
                coefficient=coefficient,
                usable_amount=usable_amount,
                conversion_reference=conversion.legal_reference if conversion is not None else None,
                expires_on=expires_on,
                is_expired=on > expires_on,
                asset_id=entry.asset_id,
            )
        )

    totals_by_perimeter: dict[str, Decimal] = {}
    for row in rows:
        if row.is_expired:
            continue
        totals_by_perimeter[row.perimeter] = totals_by_perimeter.get(row.perimeter, Decimal("0")) + row.usable_amount

    return LossPocketResult(rows=tuple(rows), totals_by_perimeter=totals_by_perimeter)


@dataclass(frozen=True)
class TaxableGainEntry:
    """Una plusvalenza realizzata (FETTA 2, `tax_realized_service.py`) da
    compensare contro lo zainetto PRIMA di considerarla imponibile."""

    trade_date: date  # data di realizzo — usata per l'ordine cronologico di compensazione
    perimeter: str
    gain_category: str
    nominal: Decimal  # plusvalenza lorda, sempre positiva
    rate: Decimal
    taxable_coefficient: Decimal
    asset_id: uuid.UUID  # sempre presente: un gain viene sempre da una vendita reale
    # Tracciabilita' verso l'evento di origine (sempre presente: un
    # `TaxableGainEntry` nasce sempre da un `ClassifiedRealizedEvent`, mai da
    # un'apertura manuale) — permette al chiamante di ricollegare l'imposta
    # calcolata al lotto/vendita specifici (es. colonna "tasse" per riga in
    # AssetDetailPage), invece di un numero per-asset senza provenienza.
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID


@dataclass(frozen=True)
class TaxableGainRow:
    trade_date: date
    perimeter: str
    gain_category: str
    nominal: Decimal
    offset_amount: Decimal  # quanto e' stato compensato con lo zainetto
    taxable_amount: Decimal  # nominal - offset_amount, mai negativo
    tax_due: Decimal  # taxable_amount * rate * taxable_coefficient
    asset_id: uuid.UUID
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID


@dataclass(frozen=True)
class TaxableGainsResult:
    rows: tuple[TaxableGainRow, ...]
    tax_due_by_perimeter: dict[str, Decimal]
    # Capacita' residua dello zainetto DOPO questa compensazione — per la UI,
    # mai scritta indietro su `LossPocketResult` (quella resta la vista
    # "prima della compensazione", auditabile separatamente).
    remaining_pocket_by_perimeter: dict[str, Decimal]
    # Stesso ordine/indice di `pocket.rows` passato in input — permette al
    # chiamante di mostrare, riga per riga, quanto di QUELLA specifica
    # minusvalenza e' gia' stato consumato da una compensazione (mai
    # scritto dentro `LossPocketRow` stesso: quella resta immutabile).
    remaining_per_row: tuple[Decimal, ...]


def compute_taxable_gains(
    gains: list[TaxableGainEntry], pocket: LossPocketResult, ruleset: TaxRuleset, on: date
) -> TaxableGainsResult:
    """Compensazione progressiva evento-per-evento (SPEC_TAX_REGIME.md
    FETTA 2): per ogni plusvalenza, PRIMA di considerarla imponibile, cerca
    capacita' disponibile nello zainetto dello STESSO perimetro con
    `can_offset` vero, consumando FIFO per anno di formazione (stessa
    `CarryForwardRule` di FETTA 1). Gli eventi si processano in ordine
    CRONOLOGICO per perimetro, mai ricalcolati "a ritroso" col senno di poi
    — una compensazione decisa oggi deve rispecchiare l'ordine reale in cui
    gli eventi sono accaduti nel tempo.

    Funzione NUOVA, non modifica `build_loss_pocket`: quella resta la vista
    onesta "quanto ho disponibile prima di consumarlo", questa la vista
    "quanto resta da tassare dopo averlo consumato" — due domande diverse,
    mai fuse in una sola funzione."""
    # Capacita' residua per riga — di default ogni riga NON scaduta parte
    # dal proprio `usable_amount` (nessuna consumata ancora); indicizzata
    # per posizione, stesso ordine di `pocket.rows`, mai il
    # `LossPocketResult` originale mutato.
    remaining_per_row: list[Decimal] = [row.usable_amount for row in pocket.rows]
    # Pool per perimetro, FIFO per anno di formazione — un
    # `[row_index, formation_date, loss_category]` per riga NON scaduta.
    pool_by_perimeter: dict[str, list[tuple[int, date, str]]] = {}
    for idx, row in enumerate(pocket.rows):
        if row.is_expired:
            continue
        pool_by_perimeter.setdefault(row.perimeter, []).append((idx, row.formation_date, row.income_category))
    for entries in pool_by_perimeter.values():
        entries.sort(key=lambda e: e[1])

    rows: list[TaxableGainRow] = []
    tax_due_by_perimeter: dict[str, Decimal] = {}

    for gain in sorted(gains, key=lambda g: (g.perimeter, g.trade_date)):
        remaining_needed = gain.nominal
        offset_amount = Decimal("0")
        for row_index, formation_date, loss_category in pool_by_perimeter.get(gain.perimeter, []):
            if remaining_needed <= 0:
                break
            available = remaining_per_row[row_index]
            if available <= 0:
                continue
            # Causalita' temporale: una minusvalenza puo' compensare solo
            # una plusvalenza REALIZZATA DOPO (o lo stesso giorno) la sua
            # formazione — mai una gia' avvenuta prima che la perdita
            # esistesse. Senza questo controllo il solo ordinamento FIFO
            # per anno di formazione lascerebbe passare una minusvalenza
            # futura a compensare una plusvalenza passata (bug reale
            # trovato dall'utente su dati di QA).
            if formation_date > gain.trade_date:
                continue
            if not ruleset.can_offset(loss_category, gain.gain_category):
                continue
            take = min(remaining_needed, available)
            remaining_per_row[row_index] -= take
            offset_amount += take
            remaining_needed -= take

        taxable_amount = gain.nominal - offset_amount
        tax_due = quantize_money(taxable_amount * gain.rate * gain.taxable_coefficient)
        rows.append(
            TaxableGainRow(
                trade_date=gain.trade_date,
                perimeter=gain.perimeter,
                gain_category=gain.gain_category,
                nominal=gain.nominal,
                offset_amount=quantize_money(offset_amount),
                taxable_amount=quantize_money(taxable_amount),
                tax_due=tax_due,
                asset_id=gain.asset_id,
                lot_transaction_id=gain.lot_transaction_id,
                sell_transaction_id=gain.sell_transaction_id,
            )
        )
        tax_due_by_perimeter[gain.perimeter] = tax_due_by_perimeter.get(gain.perimeter, Decimal("0")) + tax_due

    remaining_pocket_by_perimeter: dict[str, Decimal] = {
        perimeter: sum((remaining_per_row[idx] for idx, _fd, _cat in entries), Decimal("0"))
        for perimeter, entries in pool_by_perimeter.items()
    }

    return TaxableGainsResult(
        rows=tuple(rows),
        tax_due_by_perimeter=tax_due_by_perimeter,
        remaining_pocket_by_perimeter=remaining_pocket_by_perimeter,
        remaining_per_row=tuple(remaining_per_row),
    )

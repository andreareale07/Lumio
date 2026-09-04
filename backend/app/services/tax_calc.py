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
            )
        )

    totals_by_perimeter: dict[str, Decimal] = {}
    for row in rows:
        if row.is_expired:
            continue
        totals_by_perimeter[row.perimeter] = totals_by_perimeter.get(row.perimeter, Decimal("0")) + row.usable_amount

    return LossPocketResult(rows=tuple(rows), totals_by_perimeter=totals_by_perimeter)

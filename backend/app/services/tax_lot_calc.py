"""Motore a lotti PURO (SPEC_TAX_REGIME.md FETTA 2) — nessuna dipendenza da
DB/FastAPI, parallelo a `position_calc.py` (mai modificato: quello resta il
costo medio ponderato mobile per la valorizzazione, SPEC §34 — questo modulo
serve solo a derivare eventi realizzativi fiscali, un calcolo diverso sugli
stessi movimenti).

Il criterio di consumo dei lotti (LIFO per l'Italia, prassi Agenzia delle
Entrate) e' un DATO della giurisdizione (`TaxRuleset.lot_consumption_order`,
`app/tax/base.py`), MAI cablato qui: e' una scelta amministrativa specifica
di un paese (altri usano FIFO o identificazione specifica), non una regola
universale — stessa filosofia di `TaxJurisdiction` per aliquote/categorie.
`compute_tax_lots` riceve l'ordine come parametro esplicito.

**Non eredita la conflazione `fees + tax` di `position_calc.py`**
(righe 89/104 di quel modulo): fiscalmente `fees` e' onere accessorio
(entra nel costo del lotto/riduce il provento), `tax` e' imposta gia'
prelevata (un ESITO, mai una componente di costo o di provento) — il
realizzo si calcola SEMPRE al lordo della ritenuta.

Nessuna tabella persistita (stesso principio "derivato, non persistito"
gia' scelto per lo zainetto in FETTA 1): i lotti si ricostruiscono ogni
volta da `investment_transactions`, mai un secondo ledger da tenere
sincronizzato — un utente che corregge/retrodata un movimento non deve
produrre una divergenza silenziosa con un lotto congelato altrove.

Consumo SEMPRE per singolo `(financial_account_id, asset_id)` — MAI
aggregato tra conti diversi, nemmeno con lo stesso perimetro fiscale
(decisione presa con l'utente, marcata `FISCAL ASSUMPTION REQUIRING
VALIDATION` sotto): un broker ha una custodia fisica separata, non vede cosa
possiedi altrove. Per il perimetro dichiarativo l'aggregazione tra conti
resta ma avviene A VALLE, sullo zainetto (gia' aggregato per perimetro),
non nel consumo dei lotti stesso.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, Literal, Protocol

from app.services.movement_order import order_movements_within_day

# FISCAL ASSUMPTION REQUIRING VALIDATION: il consumo dei lotti avviene
# sempre per singolo conto, mai aggregato tra conti anche con lo stesso
# perimetro fiscale — prassi coerente con la custodia fisica separata di
# ogni intermediario in regime amministrato, non una norma esplicita per il
# perimetro dichiarativo aggregato (dove l'aggregazione avviene a valle,
# sullo zainetto). Il chiamante (tax_realized_service.py) e' responsabile
# di raggruppare i movimenti per conto PRIMA di chiamare compute_tax_lots.
ACCOUNT_SCOPED_CONSUMPTION_ASSUMPTION = (
    "FISCAL ASSUMPTION REQUIRING VALIDATION: il consumo dei lotti avviene sempre per "
    "singolo conto, mai aggregato tra conti anche con lo stesso perimetro fiscale."
)

LotConsumptionOrder = Literal["lifo", "fifo"]


class TaxMovementLike(Protocol):
    """Un movimento gia' filtrato per un SINGOLO `(financial_account_id,
    asset_id)` e ordinato per `(trade_date, created_at, id)` dal chiamante
    — questa funzione non ordina, per restare pura e testabile su liste
    costruite a mano, stesso principio di `position_calc.compute_position`."""

    id: uuid.UUID
    type: str
    trade_date: date
    quantity: Decimal | None
    price: Decimal | None
    fees: Decimal
    tax: Decimal


@dataclass(frozen=True)
class RealizedTaxEvent:
    trade_date: date  # data della VENDITA — la minus/plusvalenza si forma al realizzo, non all'acquisto
    quantity: Decimal
    proceeds: Decimal  # qty * price - fees (MAI - tax: il realizzo e' al lordo della ritenuta)
    cost_basis: Decimal  # qty * price_del_lotto + fees_allocate_del_lotto (MAI + tax)
    gain_or_loss: Decimal  # proceeds - cost_basis
    lot_formation_date: date  # data di acquisto del lotto consumato (LIFO: il piu' recente)
    # Tracciabilita' (serve sia a FETTA 2 sia alla vista "aperto/chiuso" del
    # dettaglio asset, portfolio): quale movimento ha creato il lotto e quale
    # vendita l'ha consumato — mai solo una data, che con piu' movimenti
    # nello stesso giorno sarebbe ambigua.
    lot_transaction_id: uuid.UUID
    sell_transaction_id: uuid.UUID


@dataclass
class _OpenLot:
    transaction_id: uuid.UUID
    trade_date: date
    quantity: Decimal
    unit_cost: Decimal  # (qty*price + fees) / qty al momento dell'acquisto — MAI + tax


@dataclass
class TaxLotState:
    open_lots: list[_OpenLot] = field(default_factory=list)
    realized_events: list[RealizedTaxEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def open_quantity(self) -> Decimal:
        return sum((lot.quantity for lot in self.open_lots), Decimal("0"))


def _peek_lot(open_lots: list["_OpenLot"], order: LotConsumptionOrder) -> "_OpenLot":
    return open_lots[-1] if order == "lifo" else open_lots[0]


def _pop_exhausted_lot(open_lots: list["_OpenLot"], order: LotConsumptionOrder) -> None:
    open_lots.pop() if order == "lifo" else open_lots.pop(0)


def compute_tax_lots(
    movements: Iterable[TaxMovementLike], consumption_order: LotConsumptionOrder = "lifo"
) -> TaxLotState:
    """Ricostruisce lo stack di lotti aperti e gli eventi realizzativi per
    UN SOLO `(financial_account_id, asset_id)` — il chiamante raggruppa
    prima (stesso schema di `position_calc.compute_position`).

    `consumption_order` viene da `TaxRuleset.lot_consumption_order` della
    giurisdizione vigente alla data di vendita — mai un default assunto dal
    chiamante senza passare dalla giurisdizione."""
    state = TaxLotState()

    for m in order_movements_within_day(movements):
        if m.type in ("dividend", "deposit", "withdrawal", "fee", "tax"):
            # Mai un evento di costo/vendita sul lotto — dividend e' reddito
            # di capitale (gestito come event_kind="income" a valle, non
            # tocca i lotti), gli altri sono cassa pura senza asset_id
            # (stesso `_NO_EFFECT_TYPES` di position_calc.py).
            continue

        if m.type in ("buy", "opening"):
            qty = m.quantity or Decimal("0")
            price = m.price or Decimal("0")
            if qty <= 0:
                continue
            lot_cost = qty * price + m.fees
            state.open_lots.append(
                _OpenLot(transaction_id=m.id, trade_date=m.trade_date, quantity=qty, unit_cost=lot_cost / qty)
            )

        elif m.type == "sell":
            qty_to_consume = m.quantity or Decimal("0")
            price = m.price or Decimal("0")
            if qty_to_consume <= 0:
                continue
            if qty_to_consume > state.open_quantity:
                state.warnings.append(
                    f"vendita di {qty_to_consume} il {m.trade_date} eccede la quantita' "
                    f"posseduta ({state.open_quantity}): i lotti risulteranno esauriti in anticipo"
                )
            total_proceeds = qty_to_consume * price - m.fees
            remaining = qty_to_consume
            while remaining > 0 and state.open_lots:
                lot = _peek_lot(state.open_lots, consumption_order)
                consumed_qty = min(remaining, lot.quantity)
                # Proventi ripartiti in proporzione alla quota consumata di
                # QUESTA vendita (stesso principio proporzionale di
                # position_calc.py per lo strategy_cost).
                proceeds_portion = total_proceeds * (consumed_qty / qty_to_consume)
                cost_portion = consumed_qty * lot.unit_cost
                state.realized_events.append(
                    RealizedTaxEvent(
                        trade_date=m.trade_date,
                        quantity=consumed_qty,
                        proceeds=proceeds_portion,
                        cost_basis=cost_portion,
                        gain_or_loss=proceeds_portion - cost_portion,
                        lot_formation_date=lot.trade_date,
                        lot_transaction_id=lot.transaction_id,
                        sell_transaction_id=m.id,
                    )
                )
                lot.quantity -= consumed_qty
                remaining -= consumed_qty
                if lot.quantity == 0:
                    _pop_exhausted_lot(state.open_lots, consumption_order)
            if remaining > 0:
                # Vendita oltre il posseduto (gia' segnalata sopra): la
                # porzione eccedente non ha un lotto da cui costare, niente
                # RealizedTaxEvent inventato per essa — risultato onesto,
                # mai un blocco (stesso principio di position_calc.py).
                pass

        elif m.type == "split":
            ratio = m.quantity or Decimal("1")
            if ratio > 0:
                for lot in state.open_lots:
                    lot.quantity *= ratio
                    lot.unit_cost /= ratio

        elif m.type == "adjustment":
            delta = m.quantity or Decimal("0")
            if delta > 0:
                if m.price is None:
                    state.warnings.append(
                        f"adjustment positivo il {m.trade_date} senza prezzo: nessun lotto "
                        "fiscale creato (nessun costo su cui basarlo)"
                    )
                else:
                    state.open_lots.append(
                        _OpenLot(transaction_id=m.id, trade_date=m.trade_date, quantity=delta, unit_cost=m.price)
                    )
            elif delta < 0:
                # Correzione dati, non una cessione reale: consumo
                # silenzioso nello stesso ordine, MAI un RealizedTaxEvent
                # (vedi docstring).
                remaining = -delta
                while remaining > 0 and state.open_lots:
                    lot = _peek_lot(state.open_lots, consumption_order)
                    consumed = min(remaining, lot.quantity)
                    lot.quantity -= consumed
                    remaining -= consumed
                    if lot.quantity == 0:
                        _pop_exhausted_lot(state.open_lots, consumption_order)

    return state

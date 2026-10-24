"""Ordine dei movimenti dello stesso giorno: regressione sui dati REALI di
Example dell'utente (35 operazioni, vendite registrate prima dell'acquisto
corrispondente nello stesso giorno), che producevano un utile realizzato di
+999.999 EUR su un titolo in perdita. Nessun DB."""
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.services.movement_order import order_movements_within_day
from app.services.position_calc import compute_position
from app.services.tax_lot_calc import compute_tax_lots


@dataclass
class Mv:
    trade_date: date
    type: str
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    source_type_raw: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


# (data, tipo, quantita', prezzo, importo) nell'ordine di importazione.
_ACME = [
    ("2031-03-03", "sell", "8", "40.450000", "323.60"),
    ("2031-03-03", "buy", "8", "49.270000", "-394.16"),
    ("2031-03-03", "buy", "0.5", "44.240000", "-22.12"),
    ("2031-03-03", "sell", "0.5", "53.960000", "26.98"),
]


def _acme() -> list[Mv]:
    return [
        Mv(date.fromisoformat(d), t, Decimal(q), Decimal(p), Decimal(a)) for d, t, q, p, a in _ACME
    ]


def _cash_result() -> Decimal:
    # Posizione chiusa a zero: utile realizzato = incassi - esborsi, qualunque
    # sia il metodo di costo.
    return sum((Decimal(a) for _, _, _, _, a in _ACME), Decimal("0"))


def test_same_day_sell_before_its_buy_is_deferred_after_it():
    ordered = order_movements_within_day(_acme()[:2])
    assert [m.type for m in ordered] == ["buy", "sell"]


def test_valid_sell_before_rebuy_keeps_the_original_order():
    held = Mv(date(2024, 1, 1), "buy", Decimal("10"), Decimal("100"))
    sell = Mv(date(2024, 1, 2), "sell", Decimal("10"), Decimal("110"))
    rebuy = Mv(date(2024, 1, 2), "buy", Decimal("10"), Decimal("120"))
    assert order_movements_within_day([held, sell, rebuy]) == [held, sell, rebuy]


def test_real_oversell_stays_in_place_so_the_warning_is_not_hidden():
    sell = Mv(date(2024, 1, 2), "sell", Decimal("5"), Decimal("110"))
    state = compute_position([sell])
    assert state.warnings and state.quantity == Decimal("-5")


def test_movements_without_trade_date_are_never_reordered():
    class NoDate:
        def __init__(self, type_: str, quantity: str):
            self.type, self.quantity = type_, Decimal(quantity)

    items = [NoDate("sell", "5"), NoDate("buy", "5")]
    assert order_movements_within_day(items) == items


def test_tesla_realized_matches_cash_result_not_a_million():
    state = compute_position(_acme())
    assert state.quantity == Decimal("0")
    assert state.warnings == []
    assert abs(state.realized_pl - _cash_result()) < Decimal("0.5")
    assert abs(state.realized_pl) < Decimal("5000")


def test_tesla_tax_lots_are_all_closed_and_gain_matches_cash_result():
    state = compute_tax_lots(_acme())
    assert state.open_quantity == Decimal("0")
    assert state.warnings == []
    total = sum((e.gain_or_loss for e in state.realized_events), Decimal("0"))
    assert abs(total - _cash_result()) < Decimal("0.5")

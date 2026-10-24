"""Ordine dei movimenti dello stesso giorno: l'estratto non riporta l'ora e le
righe di uno stesso giorno possono arrivare con la vendita PRIMA dell'acquisto
corrispondente. Rigiocata cosi', la vendita trovava quantita' zero, veniva
valutata a costo zero e gonfiava l'utile realizzato. I dati sono SINTETICI
(titolo e numeri inventati): riproducono solo la struttura del difetto. Nessun DB."""
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
    ("2031-03-09", "buy", "5", "48.480000", "-242.40"),
    ("2031-03-09", "sell", "5", "43.900000", "219.50"),
    ("2031-03-12", "buy", "6", "52.720000", "-316.32"),
    ("2031-03-12", "buy", "12", "47.690000", "-572.28"),
    ("2031-03-14", "sell", "18", "43.110000", "775.98"),
    ("2031-03-14", "buy", "6", "51.930000", "-311.58"),
    ("2031-03-17", "sell", "6", "47.350000", "284.10"),
    ("2031-03-17", "buy", "7", "41.870000", "-293.09"),
    ("2031-03-17", "sell", "7", "51.590000", "361.13"),
    ("2031-03-21", "buy", "20", "46.110000", "-922.20"),
    ("2031-03-21", "sell", "20", "55.830000", "1116.60"),
    ("2031-03-24", "buy", "9", "50.350000", "-453.15"),
    ("2031-03-24", "buy", "4", "45.320000", "-181.28"),
    ("2031-03-25", "sell", "9", "55.040000", "495.36"),
    ("2031-03-25", "sell", "4", "50.010000", "200.04"),
    ("2031-03-28", "sell", "5", "44.980000", "224.90"),
    ("2031-03-28", "buy", "5", "53.800000", "-269.00"),
    ("2031-03-31", "sell", "5", "49.220000", "246.10"),
    ("2031-03-31", "sell", "6", "44.190000", "265.14"),
    ("2031-03-31", "buy", "5", "53.010000", "-265.05"),
    ("2031-03-31", "buy", "5", "47.980000", "-239.90"),
    ("2031-03-31", "sell", "5", "57.700000", "288.50"),
    ("2031-03-31", "buy", "5", "52.220000", "-261.10"),
    ("2031-03-31", "sell", "5", "47.640000", "238.20"),
    ("2031-03-31", "buy", "6", "56.460000", "-338.76"),
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


def test_realized_matches_cash_result_not_an_inflated_figure():
    state = compute_position(_acme())
    assert state.quantity == Decimal("0")
    assert state.warnings == []
    assert abs(state.realized_pl - _cash_result()) < Decimal("0.5")
    # Senza l'ordine corretto ogni vendita "in anticipo" valeva tutto l'incasso.
    assert abs(state.realized_pl) < Decimal("1000")


def test_tax_lots_are_all_closed_and_gain_matches_cash_result():
    state = compute_tax_lots(_acme())
    assert state.open_quantity == Decimal("0")
    assert state.warnings == []
    total = sum((e.gain_or_loss for e in state.realized_events), Decimal("0"))
    assert abs(total - _cash_result()) < Decimal("0.5")

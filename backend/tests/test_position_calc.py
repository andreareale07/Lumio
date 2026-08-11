"""Test unitari della matematica pura di `position_calc.py` (milestone 09)
— nessuna dipendenza da DB/FastAPI, come `test_csv_parser.py` per il canale
CSV. Un semplice oggetto con gli attributi richiesti dal `MovementLike`
Protocol basta, senza toccare `InvestmentTransaction`/il DB.
"""
from dataclasses import dataclass
from decimal import Decimal

from app.services.position_calc import compute_position


@dataclass
class M:
    type: str
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")


def test_single_buy_sets_quantity_and_average_cost():
    state = compute_position([M("buy", quantity=Decimal("10"), price=Decimal("100"))])
    assert state.quantity == Decimal("10")
    assert state.average_cost == Decimal("100")
    assert state.realized_pl == Decimal("0")
    assert state.warnings == []


def test_two_buys_produce_weighted_average_cost():
    # 10 a 100 + 10 a 120 => media ponderata 110, non la media semplice.
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            M("buy", quantity=Decimal("10"), price=Decimal("120")),
        ]
    )
    assert state.quantity == Decimal("20")
    assert state.average_cost == Decimal("110")


def test_buy_fees_and_tax_increase_cost_basis():
    state = compute_position(
        [M("buy", quantity=Decimal("10"), price=Decimal("100"), fees=Decimal("5"), tax=Decimal("5"))]
    )
    # (10*100 + 5 + 5) / 10 = 101
    assert state.average_cost == Decimal("101")


def test_opening_behaves_like_buy():
    # Movimento di apertura: carica una posizione preesistente senza dover
    # ricostruire lo storico (decisione M09).
    state = compute_position([M("opening", quantity=Decimal("50"), price=Decimal("20"))])
    assert state.quantity == Decimal("50")
    assert state.average_cost == Decimal("20")


def test_partial_sell_keeps_average_cost_and_realizes_pl():
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            M("sell", quantity=Decimal("4"), price=Decimal("150")),
        ]
    )
    assert state.quantity == Decimal("6")
    # Average cost NON cambia su una vendita parziale (solo su un acquisto).
    assert state.average_cost == Decimal("100")
    # realized P/L = 4 * (150 - 100) = 200
    assert state.realized_pl == Decimal("200")
    assert state.warnings == []


def test_sell_fees_and_tax_reduce_realized_pl():
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            M("sell", quantity=Decimal("10"), price=Decimal("150"), fees=Decimal("10"), tax=Decimal("5")),
        ]
    )
    # proceeds netti = 10*150 - 10 - 5 = 1485; costo = 10*100 = 1000
    assert state.realized_pl == Decimal("485")


def test_full_sell_resets_average_cost_to_zero():
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            M("sell", quantity=Decimal("10"), price=Decimal("150")),
        ]
    )
    assert state.quantity == Decimal("0")
    assert state.average_cost == Decimal("0")


def test_sell_exceeding_quantity_warns_but_does_not_raise():
    state = compute_position(
        [
            M("buy", quantity=Decimal("5"), price=Decimal("100")),
            M("sell", quantity=Decimal("10"), price=Decimal("150")),
        ]
    )
    assert state.quantity == Decimal("-5")
    assert len(state.warnings) == 1
    assert "eccede" in state.warnings[0]


def test_split_scales_quantity_and_average_cost_inversely():
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            M("split", quantity=Decimal("2")),  # 2:1
        ]
    )
    assert state.quantity == Decimal("20")
    assert state.average_cost == Decimal("50")
    # Il valore totale della posizione non cambia con lo split.
    assert state.quantity * state.average_cost == Decimal("1000")


def test_dividend_deposit_withdrawal_have_no_effect_on_position():
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            M("dividend", amount=Decimal("50")),
            M("deposit", amount=Decimal("1000")),
            M("withdrawal", amount=Decimal("-200")),
        ]
    )
    assert state.quantity == Decimal("10")
    assert state.average_cost == Decimal("100")
    assert state.realized_pl == Decimal("0")


def test_standalone_fee_and_tax_reduce_realized_pl_without_touching_quantity():
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            M("fee", amount=Decimal("-15")),
            M("tax", amount=Decimal("-3")),
        ]
    )
    assert state.quantity == Decimal("10")
    assert state.realized_pl == Decimal("-18")


def test_adjustment_applies_delta_and_overrides_average_cost():
    # Onboarding di una posizione preesistente via modifica manuale (SPEC,
    # decisione M09): l'utente dichiara 100 unita' a costo medio 42, il
    # servizio traduce in un adjustment con delta=100 e price=42 (vedi
    # position_service.apply_manual_position_edit).
    state = compute_position([M("adjustment", quantity=Decimal("100"), price=Decimal("42"))])
    assert state.quantity == Decimal("100")
    assert state.average_cost == Decimal("42")
    assert state.realized_pl == Decimal("0")


def test_adjustment_delta_on_top_of_existing_position():
    state = compute_position(
        [
            M("buy", quantity=Decimal("10"), price=Decimal("100")),
            # Correzione: l'utente in realta' ne possiede 8, non 10 (es.
            # un buy inserito per errore) — delta = -2, nessun nuovo costo
            # medio dichiarato (price=None => average_cost invariata).
            M("adjustment", quantity=Decimal("-2"), price=None),
        ]
    )
    assert state.quantity == Decimal("8")
    assert state.average_cost == Decimal("100")


def test_idempotent_same_input_same_output():
    movements = [
        M("buy", quantity=Decimal("10"), price=Decimal("100")),
        M("sell", quantity=Decimal("3"), price=Decimal("120")),
    ]
    first = compute_position(movements)
    second = compute_position(movements)
    assert first.quantity == second.quantity
    assert first.average_cost == second.average_cost
    assert first.realized_pl == second.realized_pl

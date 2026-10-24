"""Matematica pura per il calcolo delle posizioni (SPEC §34), nessuna
dipendenza da DB/FastAPI — stessa separazione di `analytics_calc.py` per gli
analytics e `rules_engine.py` per le regole. Il lato DB-aware (lettura dei
movimenti, scrittura della riga `positions`) vive in
`app/services/position_service.py`.

Metodo scelto: COSTO MEDIO PONDERATO MOBILE, non FIFO/LIFO — decisione
esplicita (non specificata da SPEC/ROADMAP per M09): piu' semplice da
spiegare in UI ("hai comprato a una media di X"), sufficiente per un
investitore retail che non deve dichiarare plusvalenze lotto per lotto.
Se in futuro servisse FIFO per motivi fiscali, e' un cambiamento isolato a
questo modulo, non al modello dati (`InvestmentTransaction` non assume ne'
l'uno ne' l'altro metodo).

Le funzioni qui non fanno mai I/O e non lanciano eccezioni per stati "sporchi"
nei dati (es. una vendita che eccede la quantita' posseduta): accumulano un
warning e procedono con un risultato onesto (quantita' negativa segnalata),
stesso principio dei parser (`ParsedRow`/`warnings`) — la UI decide come
mostrarlo, non e' compito di questo modulo bloccare.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Protocol

from app.services.investment_strategy import classify_strategy
from app.services.movement_order import order_movements_within_day


class MovementLike(Protocol):
    """Qualunque oggetto con questi attributi puo' essere passato a
    `compute_position` — tipicamente `InvestmentTransaction`, ma anche un
    oggetto di test senza toccare il DB."""

    type: str
    quantity: Decimal | None
    price: Decimal | None
    amount: Decimal
    fees: Decimal
    tax: Decimal
    source_type_raw: str | None


@dataclass
class PositionState:
    quantity: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    realized_pl: Decimal = Decimal("0")
    warnings: list[str] = field(default_factory=list)
    # Costo ATTUALMENTE investito (non il valore di mercato) nel lotto aperto,
    # ripartito per strategia (PAC vs una tantum, SPEC dashboard interattivo)
    # — invariante mantenuta ad ogni movimento: sum(strategy_cost.values())
    # == quantity * average_cost. Bug reale che questo risolve: un titolo
    # comprato e poi rivenduto per intero continuava a contare nel totale
    # "Investimenti" anche a posizione chiusa, gonfiando il totale rispetto
    # a "Per tipo di strumento" (che vede solo le posizioni aperte) — un
    # riacquisto successivo dello stesso asset partiva quindi "sporco",
    # sommato al capitale del ciclo gia' chiuso invece che ripartire da zero
    # come fa gia' `average_cost` (vedi `test_full_sell_resets_average_cost_to_zero`).
    strategy_cost: dict[str, Decimal] = field(default_factory=dict)


# Tipi che non toccano mai quantity/average_cost/realized_pl di UN asset:
# deposit/withdrawal sono movimenti di cassa puri (in pratica non arrivano
# nemmeno qui: raggruppati per asset_id, che per questi tipi e' None) e
# dividend e' reddito, non un evento di costo/vendita sulla posizione.
_NO_EFFECT_TYPES = ("dividend", "deposit", "withdrawal")


def compute_position(movements: Iterable[MovementLike]) -> PositionState:
    """Rilegge una sequenza di movimenti (GIA' ordinata per
    (trade_date, created_at, id) dal chiamante — questa funzione non ordina,
    per restare pura e testabile su liste costruite a mano) e produce lo
    stato finale della posizione. Idempotente: chiamarla due volte sulla
    stessa lista da' sempre lo stesso risultato, nessuno stato intermedio
    nascosto.
    """
    state = PositionState()

    for m in order_movements_within_day(movements):
        if m.type in _NO_EFFECT_TYPES:
            continue

        total_cost_before = state.quantity * state.average_cost
        is_buy = False
        movement_cost = Decimal("0")

        if m.type in ("buy", "opening"):
            qty = m.quantity or Decimal("0")
            price = m.price or Decimal("0")
            movement_cost = qty * price + m.fees + m.tax
            new_quantity = state.quantity + qty
            if new_quantity != 0:
                state.average_cost = (total_cost_before + movement_cost) / new_quantity
                is_buy = True
            state.quantity = new_quantity

        elif m.type == "sell":
            qty = m.quantity or Decimal("0")
            if qty > state.quantity:
                state.warnings.append(
                    f"vendita di {qty} eccede la quantita' posseduta ({state.quantity}): "
                    "la posizione risultera' negativa, verificare i movimenti"
                )
            price = m.price or Decimal("0")
            proceeds_net = qty * price - m.fees - m.tax
            state.realized_pl += proceeds_net - qty * state.average_cost
            state.quantity -= qty
            if state.quantity == 0:
                state.average_cost = Decimal("0")

        elif m.type == "split":
            # `quantity` sul movimento e' il MOLTIPLICATORE dello split (es.
            # 2 per un 2:1), non una quantita' assoluta. Il valore totale
            # della posizione non cambia: si scala quantity e average_cost
            # in modo inverso.
            ratio = m.quantity or Decimal("1")
            if ratio > 0:
                state.quantity *= ratio
                state.average_cost /= ratio

        elif m.type == "adjustment":
            # Riconciliazione da modifica manuale della posizione (vedi
            # position_service.py): `quantity` e' un DELTA con segno da
            # applicare, `price` (se presente) sovrascrive direttamente
            # average_cost al nuovo valore desiderato dall'utente — non e'
            # un prezzo di scambio. Nessun impatto su realized_pl: e' una
            # correzione dei dati posseduti, non un evento di vendita.
            state.quantity += m.quantity or Decimal("0")
            if m.price is not None:
                state.average_cost = m.price

        elif m.type in ("fee", "tax"):
            # Fee/tax standalone (non legate a un buy/sell specifico, es.
            # una commissione di custodia trimestrale): riducono il
            # realized_pl per il loro importo netto. Le fee/tax LEGATE a un
            # trade sono gia' nei campi fees/tax del movimento buy/sell
            # stesso (vedi sopra) — contarle anche qui le conterebbe due
            # volte.
            state.realized_pl -= abs(m.amount)
            continue  # nessun impatto su quantity/average_cost/strategy_cost

        # strategy_cost: mantiene l'invariante sum(strategy_cost.values()) ==
        # quantity * average_cost dopo OGNI movimento che tocca la posizione,
        # con lo stesso costo medio ponderato (nessuna identita' di lotto,
        # decisione di modulo) — non un ledger FIFO separato.
        new_total_cost = state.quantity * state.average_cost
        if new_total_cost == 0:
            # Posizione chiusa (per vendita totale, split degenere o
            # adjustment a zero): azzera insieme ad average_cost, cosi' un
            # riacquisto successivo dello stesso asset riparte pulito, senza
            # ereditare il capitale di un ciclo gia' concluso.
            state.strategy_cost = {}
        elif is_buy:
            # Contributo esatto di QUESTO acquisto, non un'inferenza: somma
            # diretta, stessa cifra che ha appena alimentato average_cost.
            strategy = classify_strategy(m.source_type_raw)
            state.strategy_cost[strategy] = state.strategy_cost.get(strategy, Decimal("0")) + movement_cost
        elif total_cost_before != 0:
            # Sell parziale, split, o adjustment: nessuna di queste operazioni
            # ha un'informazione di strategia propria — si riscala l'intera
            # ripartizione esistente in proporzione alla variazione di costo
            # totale (== 1 per uno split, che non cambia il valore; < 1 per
            # una vendita parziale o un adjustment negativo), preservando le
            # quote relative fra le strategie gia' presenti.
            ratio = new_total_cost / total_cost_before
            state.strategy_cost = {k: v * ratio for k, v in state.strategy_cost.items()}
        else:
            # Nuovo costo comparso senza una base precedente da cui scalare
            # (es. un adjustment di apertura, onboarding senza storico) — la
            # strategia non e' nota, va onestamente in "Altro", mai persa.
            state.strategy_cost = {"other": new_total_cost}

    return state

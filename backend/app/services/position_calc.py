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


@dataclass
class PositionState:
    quantity: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    realized_pl: Decimal = Decimal("0")
    warnings: list[str] = field(default_factory=list)


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

    for m in movements:
        if m.type in _NO_EFFECT_TYPES:
            continue

        if m.type in ("buy", "opening"):
            qty = m.quantity or Decimal("0")
            price = m.price or Decimal("0")
            cost_basis = qty * price + m.fees + m.tax
            new_quantity = state.quantity + qty
            if new_quantity != 0:
                total_cost_before = state.quantity * state.average_cost
                state.average_cost = (total_cost_before + cost_basis) / new_quantity
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

    return state

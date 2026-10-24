"""Ordine di rigioco dei movimenti dello stesso giorno — matematica pura.

Il libro mastro conosce solo la DATA di un'operazione, non l'ora, e l'ordine
dei movimenti dello stesso giorno e' quello di importazione: nell'estratto
Trade Republic le righe di uno stesso giorno non sono in ordine di esecuzione
(spesso la vendita e' registrata PRIMA dell'acquisto corrispondente).
Rigiocata cosi', la vendita trova quantita' zero, viene valutata a costo medio
zero (tutto l'incasso diventa "utile") e lascia il costo medio sporco per le
operazioni successive: un utile realizzato gonfiato di ordini di grandezza su
un titolo in realta' in perdita.

Regola: dentro ciascun giorno si mantiene l'ordine originale, ma una vendita
che supererebbe la quantita' posseduta in quel momento slitta dopo i
movimenti che la coprono. Se nemmeno cosi' e' coperta (vendita scoperta
reale) resta dov'e': l'avviso a valle segnala l'incoerenza, mai nascosta.
"""
from decimal import Decimal
from typing import Iterable, Protocol, TypeVar


class _HasQuantity(Protocol):
    type: str
    quantity: Decimal | None


T = TypeVar("T", bound=_HasQuantity)


def _after(movement: _HasQuantity, quantity: Decimal) -> Decimal:
    q = movement.quantity or Decimal("0")
    if movement.type in ("buy", "opening", "adjustment"):
        return quantity + q
    if movement.type == "sell":
        return quantity - q
    if movement.type == "split":
        ratio = q if q > 0 else Decimal("1")
        return quantity * ratio
    return quantity


def _is_covered(movement: _HasQuantity, quantity: Decimal) -> bool:
    return movement.type != "sell" or (movement.quantity or Decimal("0")) <= quantity


def order_movements_within_day(movements: Iterable[T]) -> list[T]:
    """Ritorna i movimenti con l'ordine dentro ogni giorno corretto come da
    docstring di modulo. Oggetti senza `trade_date` non si riordinano mai
    (nessun giorno a cui ancorare lo scambio)."""
    items = list(movements)
    ordered: list[T] = []
    quantity = Decimal("0")
    i = 0
    while i < len(items):
        day = getattr(items[i], "trade_date", None)
        j = i + 1
        while day is not None and j < len(items) and getattr(items[j], "trade_date", None) == day:
            j += 1
        pending = items[i:j]
        while pending:
            index = next((k for k, m in enumerate(pending) if _is_covered(m, quantity)), 0)
            movement = pending.pop(index)
            quantity = _after(movement, quantity)
            ordered.append(movement)
        i = j
    return ordered

"""Serializzazione sicura dei campi Decimal ad alta scala (SPEC/CLAUDE.md:
dato finanziario, mai una rappresentazione ambigua in risposta API).

Bug reale osservato su dati utente: una posizione chiusa esattamente (es.
7 comprate, 7 vendute) produce, con l'aritmetica Decimal di Python,
`Decimal('7.0000000000') - Decimal('7.0000000000')` = `Decimal('0E-10')` —
matematicamente zero, ma la sua resa testuale di DEFAULT (`str()`, quindi
anche la serializzazione JSON di Pydantic) e' notazione scientifica
"0E-10", non "0.0000000000". La soglia e' la scala della colonna: succede
solo per `Numeric(28, 10)` (`Position.quantity`,
`InvestmentTransaction.quantity`) — a scala 6 o 2 (`average_cost`,
`realized_pl`, importi monetari in genere) l'"esponente aggiustato" non
supera la soglia di Python per passare a notazione scientifica, quindi non
serve applicarlo ovunque, solo ai campi a scala 10.

IMPORTANTE, verificato empiricamente: ne' `.quantize()` ne' ricostruire un
nuovo `Decimal` da una stringa a notazione fissa risolvono il problema — un
`Decimal` con coefficiente zero ed esponente <= -7 usa SEMPRE notazione
scientifica nel suo `str()`, qualunque sia la sua storia di costruzione
(e' una proprieta' della rappresentazione (coefficiente, esponente), non di
come vi si e' arrivati). L'unico modo affidabile e' restituire una STRINGA
gia' a notazione fissa direttamente dal serializer, mai un `Decimal`.
"""
from decimal import Decimal


def format_fixed_decimal(value: Decimal) -> str:
    """`field_serializer` Pydantic per i campi `Numeric(28, 10)` (quantita'
    di asset): ritorna sempre una stringa a notazione fissa, mai un
    `Decimal` (che rischierebbe di essere ri-serializzato in notazione
    scientifica per un valore a zero esatto)."""
    return format(value, "f")


def format_fixed_decimal_optional(value: Decimal | None) -> str | None:
    """Come `format_fixed_decimal`, per i campi opzionali (es.
    `InvestmentTransaction.quantity`, nullable per deposit/withdrawal/fee)."""
    return None if value is None else format(value, "f")

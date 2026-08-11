"""Confidence score applicativo (SPEC §28): "Non utilizzare ciecamente il
campo confidence dichiarato dall'LLM". Implementazione minima e dichiarata
tale — SPEC la descrive come "eventuale" (opzionale), non uno scoring
elaborato: applica solo un discount quando manca un segnale aggiuntivo
(merchant riconosciuto) che ancori la risposta del modello, invece di
prendere per buono il valore dichiarato.
"""
from decimal import ROUND_HALF_UP, Decimal

_DEFAULT_CONFIDENCE = 0.5
_NO_MERCHANT_DISCOUNT = 0.85


def compute_ai_confidence(raw_confidence: float | None, has_merchant: bool) -> Decimal:
    base = raw_confidence if raw_confidence is not None else _DEFAULT_CONFIDENCE
    base = max(0.0, min(1.0, base))
    if not has_merchant:
        base *= _NO_MERCHANT_DISCOUNT
    return Decimal(str(base)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

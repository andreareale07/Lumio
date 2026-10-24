"""Rilevamento di operazioni societarie dai soli movimenti registrati — nessuna
dipendenza da DB/FastAPI, stessa separazione di `position_calc.py`.

Due casi tipici che altrimenti lasciano posizioni
"aperte" per sempre:

1. Raggruppamento/frazionamento con CAMBIO DI ISIN (es. 10.000:1):
   acquisti sul vecchio ISIN, vendite sul nuovo. Lumio crea un asset per ISIN,
   quindi i due lati non si incontrano mai: il vecchio resta aperto al costo
   non scalato, il nuovo risulta in vendita scoperta. Il segnale e' nei dati:
   due asset con nome quasi uguale, quantita' (o prezzi) in rapporto standard.
2. Derivato in leva (turbo/knock-out) scaduto senza valore: nessuna riga
   nell'estratto conto, nessun prezzo di mercato, posizione aperta a costo.

Questo modulo non applica nulla: produce SUGGERIMENTI che l'utente conferma
(le correzioni manuali battono sempre l'automatismo).
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from math import log

# Fattori k = unita' VECCHIE per 1 unita' NUOVA in un raggruppamento (reverse
# split). Solo valori con reciproco decimale finito: il moltiplicatore dello
# split si salva in NUMERIC(28,10), 1/3 introdurrebbe un errore sulle quantita'.
_REVERSE_FACTORS = (2, 4, 5, 8, 10, 20, 25, 40, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000, 100000)
# Frazionamenti (forward split): unita' NUOVE per 1 vecchia.
_FORWARD_FACTORS = (2, 3, 4, 5, 8, 10, 20, 25, 50, 100)

_QUANTITY_TOLERANCE = 0.01  # le quantita' si conservano esattamente
_PRICE_TOLERANCE_WITH_QUANTITY_MATCH = 3.0  # il prezzo si muove tra i due eventi
_PRICE_TOLERANCE_PRICE_ONLY = 1.6
_MIN_NAME_SIMILARITY = 0.7
_MIN_NAME_SIMILARITY_PRICE_ONLY = 0.85
_MIN_REVERSE_FACTOR_PRICE_ONLY = 10

_DERIVATIVE_NAME_RE = re.compile(
    r"\b(turbo|knock[\s-]?out|mini[\s-]?future|faktor|warrant|zertifikat|certificate)\b",
    re.IGNORECASE,
)


def is_derivative_name(name: str) -> bool:
    return _DERIVATIVE_NAME_RE.search(name) is not None


@dataclass(frozen=True)
class AssetActivity:
    asset_id: str
    name: str
    currency: str
    net_quantity: Decimal  # somma sui conti; negativo = vendita oltre il posseduto
    first_date: date
    last_date: date
    first_price: Decimal | None
    last_price: Decimal | None


@dataclass(frozen=True)
class SplitSuggestionCalc:
    source_asset_id: str
    target_asset_id: str
    # Unita' del titolo nuovo per 1 unita' del vecchio (0.0001 per 10.000:1).
    ratio: Decimal
    split_date: date
    confidence: str  # "high" | "medium"
    quantity_matched: bool


def _compact(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _compact(a), _compact(b)).ratio()


def _nearest_factor(value: float, candidates: tuple[float, ...]) -> tuple[float, float]:
    """(fattore piu' vicino in scala logaritmica, scarto moltiplicativo >= 1)."""
    best = min(candidates, key=lambda c: abs(log(value / c)))
    spread = max(value / best, best / value)
    return best, spread


def suggest_split_date(source_last_date: date, target_first_date: date) -> date:
    """Il giorno prima del primo movimento sul titolo nuovo, mai prima
    dell'ultimo sul vecchio: `split` ordina per (data, created_at) e uno split
    creato adesso nello stesso giorno di un movimento finirebbe DOPO di lui."""
    candidate = target_first_date - timedelta(days=1)
    return max(candidate, source_last_date)


def detect_split_suggestions(activities: list[AssetActivity]) -> list[SplitSuggestionCalc]:
    suggestions: list[SplitSuggestionCalc] = []
    for source in activities:
        if source.net_quantity <= 0 or not source.last_price or source.last_price <= 0:
            continue
        best: SplitSuggestionCalc | None = None
        for target in activities:
            if target.asset_id == source.asset_id or target.currency != source.currency:
                continue
            if target.first_date < source.last_date:
                continue
            similarity = name_similarity(source.name, target.name)
            if similarity < _MIN_NAME_SIMILARITY:
                continue
            if not target.first_price or target.first_price <= 0:
                continue

            price_factor = float(target.first_price / source.last_price)  # >1 = raggruppamento
            candidate = _evaluate_pair(source, target, similarity, price_factor)
            if candidate is not None and (best is None or candidate.confidence == "high"):
                best = candidate
        if best is not None:
            suggestions.append(best)
    return suggestions


def _evaluate_pair(
    source: AssetActivity, target: AssetActivity, similarity: float, price_factor: float
) -> SplitSuggestionCalc | None:
    split_date = suggest_split_date(source.last_date, target.first_date)

    if target.net_quantity < 0:
        quantity_factor = float(source.net_quantity / -target.net_quantity)
        if quantity_factor >= 1:
            factor, spread = _nearest_factor(quantity_factor, tuple(float(f) for f in _REVERSE_FACTORS))
            multiplier = Decimal(1) / Decimal(int(factor))
        else:
            inverse, spread = _nearest_factor(1 / quantity_factor, tuple(float(f) for f in _FORWARD_FACTORS))
            factor = 1 / inverse
            multiplier = Decimal(int(inverse))
        if spread <= 1 + _QUANTITY_TOLERANCE:
            price_spread = max(price_factor / factor, factor / price_factor)
            if price_spread <= _PRICE_TOLERANCE_WITH_QUANTITY_MATCH:
                return SplitSuggestionCalc(
                    source_asset_id=source.asset_id,
                    target_asset_id=target.asset_id,
                    ratio=multiplier,
                    split_date=split_date,
                    confidence="high",
                    quantity_matched=True,
                )

    # Nessun riscontro sulle quantita' (il titolo nuovo non e' stato venduto
    # oltre il posseduto): solo il salto di prezzo, con requisiti piu' severi
    # perche' un salto di prezzo da solo e' un indizio debole.
    if price_factor > 1 and similarity >= _MIN_NAME_SIMILARITY_PRICE_ONLY:
        reverse = tuple(float(f) for f in _REVERSE_FACTORS if f >= _MIN_REVERSE_FACTOR_PRICE_ONLY)
        factor, spread = _nearest_factor(price_factor, reverse)
        if spread <= _PRICE_TOLERANCE_PRICE_ONLY:
            return SplitSuggestionCalc(
                source_asset_id=source.asset_id,
                target_asset_id=target.asset_id,
                ratio=Decimal(1) / Decimal(int(factor)),
                split_date=split_date,
                confidence="medium",
                quantity_matched=False,
            )
    return None

"""Estrazione del merchant dalla descrizione grezza di una transazione —
puro, nessuna dipendenza da DB, stessa natura di `csv_import.py`.

`Transaction.merchant` esiste dalla milestone 03 ma non e' mai stato
valorizzato da nessun parser: le regole `merchant_equals`, il breakdown
`by_merchant` (sempre "Senza merchant") e lo sconto di confidence per
"merchant assente" (`app/services/confidence.py`, applicato SEMPRE finora)
sono tutte feature gia' scritte ma dormienti. Questo modulo le risveglia in
un colpo solo.

Pipeline di pulizia (ogni passo testato singolarmente in
`tests/test_merchant_extraction.py`):
1. NFKD + rimozione accenti, maiuscolo, collasso spazi.
2. Strip dei prefissi da strumento di pagamento (POS, PAGOBANCOMAT, SDD,
   PayPal/SumUp/Square...) — non sono il merchant, sono COME si e' pagato.
3. Strip del rumore inline: date, orari, maschere di carta, codici ID/AUT,
   run di cifre lunghe.
4. Strip della coda geografica (citta'/paese finali).
5. Alias (`app/classification/merchant_aliases.py`) per i merchant piu'
   comuni, applicati sul testo gia' ripulito.
6. Troncamento ai primi token residui (un merchant leggibile e' corto).

Ritorna `None` quando non resta nulla di sensato — MAI una stringa vuota o
il residuo di un solo carattere: un `merchant` spazzatura sarebbe peggio di
nessun merchant (le regole/il breakdown lo tratterebbero come un valore
reale).
"""
import re
import unicodedata

from app.classification.merchant_aliases import MERCHANT_ALIASES

_PREFIX_PATTERNS = [
    re.compile(r"^PAGAMENTO\s+POS\b\s*"),
    re.compile(r"^POS\b\s*"),
    re.compile(r"^PAGOBANCOMAT\b\s*"),
    re.compile(r"^ACQUISTO\s+CARTA\b\s*"),
    re.compile(r"^ADDEBITO\s+SDD\b\s*"),
    re.compile(r"^SEPA\s+DD\b\s*"),
    re.compile(r"^PAYPAL\s*\*\s*"),
    re.compile(r"^SUMUP\s*\*\s*"),
    re.compile(r"^SQ\s*\*\s*"),
    re.compile(r"^SP\s*\*\s*"),
]

_NOISE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b"),  # date
    re.compile(r"\b\d{1,2}:\d{2}\b"),  # orari
    re.compile(r"\*{2,}\d{2,6}\b"),  # maschere carta ****1234
    re.compile(r"\bX{2,}\d{2,6}\b"),  # XXXX1234
    re.compile(r"\bCARTA\s*N\.?\s*\d+\b"),
    re.compile(r"\bID\.?\s*[A-Z0-9]{6,}\b"),
    re.compile(r"\bAUT\.?\s*\d+\b"),
    re.compile(r"\b\d{6,}\b"),  # run di cifre lunghe (riferimenti operazione)
]

# Coda geografica: solo i casi piu' comuni e non ambigui (un token che e'
# ESATTAMENTE uno di questi, in coda al testo). Non esaustivo di proposito —
# estendere quando emerge un caso reale, non a priori (stessa posizione gia'
# presa per `country` in catalog.py).
_GEO_TAIL = {
    "ITALIA", "ITA", "IT", "MILANO", "ROMA", "TORINO", "NAPOLI", "BOLOGNA",
    "FIRENZE", "GENOVA", "PALERMO", "VENEZIA", "VERONA", "BARI", "CATANIA",
}

_MAX_TOKENS = 4


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", without_accents.upper()).strip()


def _strip_prefix(text: str) -> str:
    for pattern in _PREFIX_PATTERNS:
        stripped = pattern.sub("", text, count=1)
        if stripped != text:
            return stripped.strip()
    return text


def _strip_noise(text: str) -> str:
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_geo_tail(text: str) -> str:
    tokens = text.split(" ")
    while tokens and tokens[-1] in _GEO_TAIL:
        tokens.pop()
    return " ".join(tokens)


def _apply_alias(text: str) -> str | None:
    # Confine di parola, non semplice sottostringa: stessa regola
    # anti-falso-positivo del catalogo di pattern (catalog.py) — "COOP" deve
    # matchare "COOP SUPERMERCATO" ma non "COOPERATIVA EDILE SRL".
    for key, display_name in MERCHANT_ALIASES.items():
        if re.search(rf"\b{re.escape(key)}\b", text):
            return display_name
    return None


def extract_merchant(description_raw: str) -> str | None:
    normalized = _normalize(description_raw)
    normalized = _strip_prefix(normalized)
    normalized = _strip_noise(normalized)
    normalized = _strip_geo_tail(normalized)

    alias = _apply_alias(normalized)
    if alias is not None:
        return alias

    tokens = [t for t in normalized.split(" ") if t]
    if not tokens:
        return None

    tokens = tokens[:_MAX_TOKENS]
    # Un singolo token di 1-2 caratteri residuo (es. un frammento di codice
    # non riconosciuto dal noise-stripping) non e' un merchant leggibile.
    if len(tokens) == 1 and len(tokens[0]) <= 2:
        return None
    # Un residuo interamente numerico (un riferimento operazione che il
    # noise-stripping non ha riconosciuto, es. un numero a 5 cifre sotto la
    # soglia di 6 di `_NOISE_PATTERNS`) non e' mai un nome di merchant.
    if all(t.isdigit() for t in tokens):
        return None

    return " ".join(tokens).title()

"""Estrazione strutturata dei movimenti Trade Republic dalla colonna
DESCRIZIONE dei movimenti "Commercio" (milestone 09c).

Formato osservato — verificato sui dati REALI dell'utente (48/48 righe
esistenti matchano questo pattern, zero eccezioni, vedi sessione di
sviluppo M09):

    "{verbo} {ISIN} {nome}, quantity: {quantita}"

- "Savings plan execution" -> PAC (piano di accumulo), quantita' frazionaria.
- "Buy trade" / "Sell trade" -> ordine singolo.

Decisione di prodotto dichiarata e concordata con l'utente: la commissione
per trade (oggi ~1€ per gli ordini singoli, gratuita per il PAC) e' GIA'
inclusa nell'importo totale della transazione bancaria e non viene
scorporata qui — si calcola un prezzo medio EFFETTIVO (importo / quantita'),
con `fees=0`. L'impatto in cassa resta sempre esattamente corretto (e' cio'
che conta per patrimonio/cash flow); il costo medio per azione e' quello
"effettivo" (prezzo di borsa + commissione spalmata sulla quantita'), non il
prezzo di borsa puro — differenza di pochi centesimi per azione, sempre
correggibile a mano dall'utente se un giorno servisse la precisione al
centesimo. Evita di dover assumere un importo di commissione esatto che
potrebbe cambiare o variare per strumento.

Nessuna riga fuori da questi 3 verbi e' stata osservata (niente "Dividendo"
ancora, che infatti oggi ricade sul fallback generico di
`trade_republic.py:_transaction_type`): se in futuro emergesse un nuovo
formato, `parse_trade_description` ritorna semplicemente `None` — mai
un'eccezione, mai un dato inventato (SPEC "human in the loop"). Punto di
estensione naturale per un fallback AI opzionale quando il regex non
matcha, non implementato qui perche' oggi non ha nessun caso reale da
risolvere (0/48 righe) — costruirlo ora sarebbe complessita' speculativa.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_PATTERN = re.compile(
    r"^(?P<verb>Savings plan execution|Buy trade|Sell trade) "
    r"(?P<isin>[A-Z]{2}[A-Z0-9]{9}[0-9]) "
    r"(?P<name>.+), quantity: (?P<quantity>\d+(?:\.\d+)?)$"
)

_VERB_TO_TYPE = {
    "Savings plan execution": "buy",
    "Buy trade": "buy",
    "Sell trade": "sell",
}


@dataclass(frozen=True)
class ParsedTrade:
    type: str  # "buy" | "sell"
    isin: str
    asset_name: str
    quantity: Decimal
    source_type_raw: str  # il verbo originale (distingue PAC da ordine singolo)


def parse_trade_description(description_raw: str) -> ParsedTrade | None:
    """Ritorna `None` se la descrizione non matcha il formato riconosciuto —
    la transazione bancaria resta comunque valida, semplicemente senza un
    `InvestmentTransaction` derivato automaticamente (l'utente puo' sempre
    registrarlo a mano dalla UI)."""
    match = _PATTERN.match(description_raw.strip())
    if match is None:
        return None
    try:
        quantity = Decimal(match.group("quantity"))
    except InvalidOperation:
        return None
    if quantity <= 0:
        return None
    verb = match.group("verb")
    return ParsedTrade(
        type=_VERB_TO_TYPE[verb],
        isin=match.group("isin"),
        asset_name=match.group("name").strip(),
        quantity=quantity,
        source_type_raw=verb,
    )

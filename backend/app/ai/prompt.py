"""Costruzione del prompt e parsing della risposta, condivisi da tutti i
provider (Ollama/OpenAI/Anthropic/Custom parlano tutti "prompt di testo in,
JSON out" anche se il trasporto HTTP differisce) — evita di duplicare questa
logica in ogni provider concreto.

Rework prompt AI (post rifondazione tassonomia): rispetto alla versione
precedente, il prompt ora:
- espone la gerarchia (raggruppata per padre) invece di una lista piatta;
- include gli hint di disambiguazione dove esistono
  (`app/classification/taxonomy.py`);
- separa system prompt (istruzioni + few-shot, stabile) da user prompt
  (la singola transazione, variabile) — `build_messages` per i provider con
  un vero ruolo system, `build_prompt` (concatenazione) per quelli senza
  (Ollama `/api/generate`);
- espone `transaction_type`/`transaction_date`/`counterparty_name` oltre a
  descrizione/merchant/importo;
- offre un JSON Schema (`response_schema`) per i provider con structured
  output nativo, con `category_code` vincolato a un enum dei code
  effettivamente offerti — rende "il modello inventa un code" strutturalmente
  impossibile dove supportato. Il guard su un code non riconosciuto
  (`parse_payload`) resta comunque l'unica difesa per i provider senza
  schema, ed e' un'invariante testata a prescindere.
"""
import json
import re
from dataclasses import dataclass

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM_INSTRUCTIONS = (
    "Sei un classificatore di transazioni finanziarie personali per un utente italiano.\n"
    "Ricevi una transazione bancaria e un elenco di categorie ammesse, raggruppate per gruppo.\n"
    "Scegli SEMPRE una categoria specifica (mai il nome di un gruppo) che descriva lo SCOPO "
    "della spesa o dell'entrata, non lo strumento di pagamento.\n"
    "Se nessuna categoria e' un match ragionevole, rispondi con category_code null: "
    "e' una risposta legittima, meglio astenersi che indovinare.\n\n"
    "Esempi:\n"
    '- descrizione: "ENI STAZIONE DI SERVIZIO MILANO", merchant: "Eni" -> trasporti.carburante\n'
    '- descrizione: "PAGAMENTO POS LIDL ITALIA SRL", merchant: "Lidl" -> alimentari.supermercato\n'
    '- descrizione: "PAGAMENTO POS FARMACIA CENTRALE", merchant: "Farmacia" -> salute.farmacia\n'
    '- descrizione: "NETFLIX.COM", merchant: "Netflix" -> abbonamenti.streaming\n'
    '- descrizione: "PAGAMENTO POS RISTORANTE DA MARIO", merchant: sconosciuto '
    "-> bar_ristoranti.ristorante\n"
    '- descrizione: "PAGAMENTO POS PANIFICIO ROSSI", merchant: sconosciuto '
    "-> alimentari.panetteria_macelleria\n"
    '- descrizione: "ADDEBITO SDD MANDATO 000123456789", merchant: sconosciuto -> nessuna (null)\n\n'
    "Rispondi SOLO con un oggetto JSON, senza testo aggiuntivo, nel formato:\n"
    '{"category_code": "<code oppure null>", "confidence": <numero 0.0-1.0>, '
    '"reason": "<spiegazione breve>"}'
)


@dataclass(frozen=True)
class PromptBundle:
    system: str
    user: str


def _render_categories(categories: list[CategoryOption]) -> str:
    """Raggruppate per padre (intestazione ## Nome padre), non una lista
    piatta: da' al modello il frame semantico del gruppo (SPEC di rework:
    "che tipo di spesa e'" prima di "quale sottocategoria esatta") a un
    costo in token minimo."""
    groups: dict[str, list[CategoryOption]] = {}
    order: list[str] = []
    for option in categories:
        header = option.parent_name or option.name
        if header not in groups:
            groups[header] = []
            order.append(header)
        groups[header].append(option)

    lines = []
    for header in order:
        lines.append(f"## {header}")
        for option in groups[header]:
            hint_suffix = f" — {option.hint}" if option.hint else ""
            lines.append(f"- {option.code}: {option.name}{hint_suffix}")
    return "\n".join(lines)


def _render_transaction(transaction: ClassifiableTransaction) -> str:
    lines = ["Transazione da classificare:"]
    if transaction.transaction_date:
        lines.append(f"data: {transaction.transaction_date}")
    lines.append(f"descrizione: {transaction.description_normalized or transaction.description_raw}")
    lines.append(f"merchant: {transaction.merchant or 'sconosciuto'}")
    if transaction.counterparty_name:
        lines.append(f"controparte: {transaction.counterparty_name}")
    lines.append(f"importo: {transaction.amount} {transaction.currency}")
    lines.append(f"direzione: {transaction.direction}")
    lines.append(f"tipo movimento: {transaction.transaction_type}")
    return "\n".join(lines)


def build_messages(transaction: ClassifiableTransaction, categories: list[CategoryOption]) -> PromptBundle:
    user = (
        f"Categorie disponibili:\n{_render_categories(categories)}\n\n"
        f"{_render_transaction(transaction)}"
    )
    return PromptBundle(system=_SYSTEM_INSTRUCTIONS, user=user)


def build_prompt(transaction: ClassifiableTransaction, categories: list[CategoryOption]) -> str:
    """Concatenazione system+user in un unico prompt di testo — per i
    provider senza un vero ruolo system separato (Ollama `/api/generate`,
    server custom minimali)."""
    bundle = build_messages(transaction, categories)
    return f"{bundle.system}\n\n{bundle.user}"


def response_schema(categories: list[CategoryOption]) -> dict:
    """JSON Schema per i provider con structured output nativo (OpenAI
    `json_schema`, Ollama `format`). `category_code` vincolato a un enum dei
    code REALMENTE offerti (+ null): dove il provider rispetta lo schema,
    il modello non puo' proprio inventare un code inesistente."""
    codes = [c.code for c in categories]
    return {
        "type": "object",
        "properties": {
            "category_code": {"enum": codes + [None]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string"},
        },
        "required": ["category_code", "confidence", "reason"],
        "additionalProperties": False,
    }


def parse_payload(payload: dict, categories: list[CategoryOption]) -> AIClassificationResult | None:
    """Cuore del parsing, isolato da come il payload e' stato ottenuto
    (regex su testo libero per i provider senza schema, direttamente un
    dict per Anthropic tool-use) — stesso guard in entrambi i casi: un code
    non tra quelli offerti equivale a "nessuna classificazione" (SPEC §86,
    il DB resta source of truth), mai una categoria forzata."""
    category_code = payload.get("category_code")
    if not category_code:
        return None

    by_code = {c.code: c for c in categories}
    category = by_code.get(category_code)
    if category is None:
        return None

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None

    reason = payload.get("reason")
    reason = reason if isinstance(reason, str) else None

    return AIClassificationResult(category_id=category.id, raw_confidence=confidence, explanation=reason)


def parse_response(raw_text: str, categories: list[CategoryOption]) -> AIClassificationResult | None:
    match = _JSON_BLOCK.search(raw_text)
    if match is None:
        raise AIProviderError(f"risposta del provider non contiene JSON: {raw_text[:200]!r}")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"JSON non valido nella risposta del provider: {exc}") from exc
    return parse_payload(payload, categories)

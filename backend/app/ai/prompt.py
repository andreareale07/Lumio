"""Costruzione del prompt e parsing della risposta, condivisi da tutti i
provider (Ollama/OpenAI/Anthropic/Custom parlano tutti "prompt di testo in,
JSON out" anche se il trasporto HTTP differisce) — evita di duplicare questa
logica in ogni provider concreto.
"""
import json
import re

from app.ai.base import AIClassificationResult, AIProviderError, CategoryOption, ClassifiableTransaction

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def build_prompt(transaction: ClassifiableTransaction, categories: list[CategoryOption]) -> str:
    category_lines = "\n".join(f"- {c.code}: {c.name}" for c in categories)
    return (
        "Sei un classificatore di transazioni finanziarie personali. "
        "Scegli la categoria piu' adatta tra quelle elencate, oppure nessuna "
        "se non c'e' un match ragionevole.\n\n"
        f"Categorie disponibili:\n{category_lines}\n\n"
        "Transazione:\n"
        f"descrizione: {transaction.description_normalized or transaction.description_raw}\n"
        f"merchant: {transaction.merchant or 'sconosciuto'}\n"
        f"importo: {transaction.amount} {transaction.currency}\n"
        f"direzione: {transaction.direction}\n\n"
        "Rispondi SOLO con un oggetto JSON, senza testo aggiuntivo, nel formato:\n"
        '{"category_code": "<code oppure null>", "confidence": <numero 0.0-1.0>, '
        '"reason": "<spiegazione breve>"}'
    )


def parse_response(raw_text: str, categories: list[CategoryOption]) -> AIClassificationResult | None:
    match = _JSON_BLOCK.search(raw_text)
    if match is None:
        raise AIProviderError(f"risposta del provider non contiene JSON: {raw_text[:200]!r}")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"JSON non valido nella risposta del provider: {exc}") from exc

    category_code = payload.get("category_code")
    if not category_code:
        return None

    by_code = {c.code: c for c in categories}
    category = by_code.get(category_code)
    if category is None:
        # Il modello ha inventato/alterato un code non tra quelli offerti:
        # nessuna categoria forzata (SPEC §86, il DB resta source of truth).
        return None

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None

    reason = payload.get("reason")
    reason = reason if isinstance(reason, str) else None

    return AIClassificationResult(
        category_id=category.id, raw_confidence=confidence, explanation=reason
    )

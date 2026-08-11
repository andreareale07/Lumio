"""Factory che risolve il provider concreto da un profilo `AIProfile` (SPEC
§25). Stesso ruolo di `app/parsers/__init__.py` per i `BankParser`: unico
punto che conosce l'elenco dei provider disponibili — aggiungerne uno nuovo
significa implementare `AIClassifier` e aggiungere un ramo qui, nessuna
modifica al dominio transazioni/import.

La API key viene decifrata solo qui, al momento dell'uso, mai altrove
(schemas/API restituiscono sempre `api_key_set`, mai il valore).
"""
from app.ai.base import AIClassifier
from app.ai.providers.anthropic import AnthropicClassifier
from app.ai.providers.custom import CustomClassifier
from app.ai.providers.noai import NoAIClassifier
from app.ai.providers.ollama import OllamaClassifier
from app.ai.providers.openai import OpenAIClassifier
from app.core.crypto import decrypt_secret
from app.models.ai_profile import AIProfile


def build_classifier(profile: AIProfile | None) -> AIClassifier:
    """`profile=None` significa "nessun profilo attivo per questo
    workspace" (SPEC §25, AI disabilitata) — non un errore, ritorna
    semplicemente `NoAIClassifier`."""
    if profile is None:
        return NoAIClassifier()

    api_key = decrypt_secret(profile.api_key_encrypted) if profile.api_key_encrypted else None

    if profile.provider == "ollama":
        return OllamaClassifier(endpoint=profile.endpoint or "", model=profile.model or "")
    if profile.provider == "openai":
        return OpenAIClassifier(api_key=api_key or "", model=profile.model or "")
    if profile.provider == "anthropic":
        return AnthropicClassifier(api_key=api_key or "", model=profile.model or "")
    if profile.provider == "custom":
        return CustomClassifier(endpoint=profile.endpoint or "", api_key=api_key, model=profile.model or "")

    return NoAIClassifier()

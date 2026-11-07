"""Validazione degli URL che arrivano dal provider e finiscono nel browser.

L'URL di autorizzazione porta il browser dell'utente fuori da Lumio
(`window.location.assign`): uno schema diverso da https (`javascript:`,
`data:`) eseguirebbe codice nell'origine dell'app. I loghi sono caricati
direttamente dal browser: solo https, mai http.
"""
from urllib.parse import urlsplit

from app.core.config import get_settings

_MAX_URL_LENGTH = 2048


def _allowed_schemes() -> tuple[str, ...]:
    # Il mock locale del provider (sviluppo) gira su http://localhost: in quel
    # caso, e solo in quel caso, anche http e' ammesso.
    if get_settings().open_banking_base_url.startswith("http://"):
        return ("https", "http")
    return ("https",)


def safe_provider_url(value: object) -> str | None:
    """L'URL se e' assoluto, con schema ammesso, host e senza credenziali
    incorporate; altrimenti `None`."""
    if not isinstance(value, str) or not value or len(value) > _MAX_URL_LENGTH:
        return None
    if any(ord(ch) < 0x21 or ord(ch) == 0x7F for ch in value):
        return None
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in _allowed_schemes() or not hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    return value

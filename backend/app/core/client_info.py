"""Dati del client (IP, user agent) da inoltrare a terzi, validati.

L'IP e' SOLO `request.client.host`: dietro nginx lo risolve uvicorn da
`X-Forwarded-For` (`--proxy-headers`, limitato alle reti dei proxy fidati,
vedi Dockerfile e nginx.conf). Leggere l'header a mano, come si faceva, lascia
decidere al client quale IP dichiarare alla banca.
"""
import ipaddress

from fastapi import Request

_MAX_USER_AGENT_LENGTH = 256


def client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def clean_user_agent(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = "".join(ch for ch in value if 0x20 <= ord(ch) < 0x7F).strip()
    return cleaned[:_MAX_USER_AGENT_LENGTH] or None

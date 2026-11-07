"""Chiamate HTTP in uscita verso indirizzi decisi dall'utente (endpoint AI,
market data personalizzato) o dal provider (loghi delle banche).

Un client normale seguirebbe qualunque indirizzo: l'utente potrebbe puntare
l'app ai servizi interni o ai metadati del cloud (SSRF). `guarded_client`
controlla ogni richiesta PRIMA dell'invio, anche l'IP risolto dal DNS:
- sempre vietati: link-local (169.254.0.0/16, fe80::/10, quindi i metadati
  cloud), non specificati, multicast, riservati;
- con `public_only=True` solo indirizzi pubblici (loghi, dati del provider).
Gli endpoint dell'utente (Ollama in LAN, server AI locali) restano ammessi.
Residuo: tra il controllo DNS e la connessione un DNS ostile potrebbe cambiare
risposta (rebinding); per questo i redirect sono disattivati di default.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

_CLOUD_METADATA_V6 = ipaddress.ip_address("fd00:ec2::254")


class OutboundBlocked(httpx.TransportError):
    """Richiesta in uscita rifiutata dalla policy (derivata da `TransportError`:
    i chiamanti che gestiscono `httpx.HTTPError` la trattano come irraggiungibile)."""


def _forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, public_only: bool) -> bool:
    if ip.is_loopback:
        # `::1` ricade in `::/8`, che `ipaddress` marca come riservato: il
        # loopback va deciso qui (ammesso per gli endpoint dell'utente).
        return public_only
    if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip == _CLOUD_METADATA_V6:
        return True
    return public_only and not ip.is_global


def check_url_syntax(url: str, *, schemes: tuple[str, ...] = ("http", "https")) -> None:
    """Controllo senza rete: schema, host, niente credenziali incorporate, IP
    letterale non vietato. Solleva `ValueError`."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError as exc:
        raise ValueError("URL non valido") from exc
    if parts.scheme.lower() not in schemes or not host:
        raise ValueError(f"URL non valido: schema ammesso {'/'.join(schemes)} e host obbligatorio")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL non valido: credenziali incorporate non ammesse")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        return
    if _forbidden(literal, public_only=False):
        raise ValueError("Indirizzo non ammesso (link-local o riservato)")


async def ensure_outbound_allowed(url: str, *, public_only: bool = False, schemes: tuple[str, ...] = ("http", "https")) -> None:
    try:
        check_url_syntax(url, schemes=schemes)
    except ValueError as exc:
        raise OutboundBlocked(str(exc)) from exc
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
        except OSError:
            # Non risolvibile: la richiesta fallira' da sola, nessun IP da vietare.
            return
        addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    if any(_forbidden(ip, public_only=public_only) for ip in addresses):
        raise OutboundBlocked("Indirizzo di destinazione non ammesso")


def guarded_client(*, public_only: bool = False, **kwargs) -> httpx.AsyncClient:
    """`httpx.AsyncClient` che applica la policy a ogni richiesta (redirect compresi,
    se abilitati). Nessun redirect per default."""

    async def _check(request: httpx.Request) -> None:
        await ensure_outbound_allowed(str(request.url), public_only=public_only)

    hooks = kwargs.pop("event_hooks", {}) or {}
    hooks = {**hooks, "request": [*hooks.get("request", []), _check]}
    kwargs.setdefault("follow_redirects", False)
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)

"""Proxy dei loghi delle banche.

Il browser non deve contattare il sito che ospita i loghi: quel sito vedrebbe
l'IP dell'utente (e quando apre l'elenco banche). Lumio scarica il logo dal
SERVER, lo tiene in cache e lo serve dalla propria origine.

Sicurezza:
- l'endpoint pubblico serve solo chiavi opache registrate da un elenco banche
  richiesto da un utente autenticato (mai un URL scelto dal chiamante);
- il download passa dal client protetto (solo https, solo IP pubblici, nessun
  redirect), con timeout e tetto di dimensione;
- solo PNG/JPEG/WEBP/GIF verificati dai byte iniziali, MAI SVG (puo' contenere
  script); la risposta e' `nosniff` e con CSP `sandbox`.
"""
import hashlib
import logging

import httpx

from app.core.outbound import guarded_client
from app.core.redis import redis_client

logger = logging.getLogger("lumio.openbanking.logos")

LOGO_TTL_SECONDS = 24 * 3600
MISS_TTL_SECONDS = 10 * 60
MAX_LOGO_BYTES = 150 * 1024
_FETCH_TIMEOUT_SECONDS = 5.0


def logo_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def logo_path(key: str) -> str:
    return f"/api/v1/open-banking/logos/{key}"


def _url_key(key: str) -> str:
    return f"ob:logo:url:{key}"


def _img_key(key: str) -> str:
    return f"ob:logo:img:{key}"


def _miss_key(key: str) -> str:
    return f"ob:logo:miss:{key}"


async def register_logos(urls: list[str]) -> dict[str, str]:
    """Registra gli URL ammessi e ritorna `{url: percorso_locale}`."""
    mapping = {url: logo_key(url) for url in urls}
    if mapping:
        async with redis_client.pipeline(transaction=False) as pipe:
            for url, key in mapping.items():
                pipe.set(_url_key(key), url, ex=LOGO_TTL_SECONDS)
            await pipe.execute()
    return {url: logo_path(key) for url, key in mapping.items()}


def sniff_image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _download(url: str) -> bytes | None:
    try:
        async with guarded_client(public_only=True, timeout=_FETCH_TIMEOUT_SECONDS) as client:
            async with client.stream("GET", url, headers={"Accept": "image/png,image/jpeg,image/webp,image/gif"}) as response:
                if response.status_code != 200:
                    return None
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_LOGO_BYTES:
                    return None
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_LOGO_BYTES:
                        return None
                return bytes(data)
    except httpx.HTTPError as exc:
        logger.info("logo non scaricabile (%s)", type(exc).__name__)
        return None


async def get_logo(key: str) -> tuple[bytes, str] | None:
    """`(byte, content_type)` oppure `None` (chiave sconosciuta, download
    fallito o contenuto non ammesso)."""
    cached = await redis_client.get(_img_key(key))
    if cached:
        content_type = sniff_image_type(cached)
        return (cached, content_type) if content_type else None
    if await redis_client.exists(_miss_key(key)):
        return None
    raw_url = await redis_client.get(_url_key(key))
    if not raw_url:
        return None
    data = await _download(raw_url.decode())
    content_type = sniff_image_type(data) if data else None
    if not data or not content_type:
        await redis_client.set(_miss_key(key), "1", ex=MISS_TTL_SECONDS)
        return None
    await redis_client.set(_img_key(key), data, ex=LOGO_TTL_SECONDS)
    return data, content_type

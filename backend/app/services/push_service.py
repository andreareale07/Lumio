"""Notifiche push all'app mobile via Firebase Cloud Messaging (HTTP v1).

Opzionale come l'AI: senza `FCM_SERVICE_ACCOUNT_FILE` ogni funzione e' un no-op.
Nessuna dipendenza nuova: il JWT del service account si firma con PyJWT +
cryptography (gia' presenti) e le chiamate usano httpx. I testi delle notifiche
non contengono mai importi ne' dati bancari: passano da Google e compaiono sulla
schermata di blocco.
"""
import json
import logging
import time
import uuid
from functools import lru_cache
from pathlib import Path

import httpx
import jwt
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.base import async_session_factory
from app.db.rls import set_rls_current_user
from app.models.push_device import PushDevice

logger = logging.getLogger("lumio.push")

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TIMEOUT = httpx.Timeout(10.0)

_cached_access_token: tuple[str, float] | None = None


@lru_cache(maxsize=1)
def _credentials(path: str) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.error("file service account FCM non leggibile (%s)", path)
        return None
    if not all(k in data for k in ("client_email", "private_key", "project_id")):
        logger.error("file service account FCM incompleto")
        return None
    return data


def _load() -> dict | None:
    path = get_settings().fcm_service_account_file
    return _credentials(path) if path else None


def is_configured() -> bool:
    return _load() is not None


async def _access_token(client: httpx.AsyncClient, creds: dict) -> str:
    global _cached_access_token
    now = time.time()
    if _cached_access_token and _cached_access_token[1] - 60 > now:
        return _cached_access_token[0]
    token_uri = creds.get("token_uri", "https://oauth2.googleapis.com/token")
    assertion = jwt.encode(
        {"iss": creds["client_email"], "scope": _SCOPE, "aud": token_uri, "iat": int(now), "exp": int(now) + 3600},
        creds["private_key"],
        algorithm="RS256",
    )
    response = await client.post(
        token_uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
    )
    response.raise_for_status()
    body = response.json()
    _cached_access_token = (body["access_token"], now + int(body.get("expires_in", 3600)))
    return _cached_access_token[0]


async def _send_one(
    client: httpx.AsyncClient, creds: dict, access_token: str, device_token: str, title: str, body: str
) -> str:
    """Ritorna 'ok', 'invalid' (token da eliminare) o 'error'."""
    response = await client.post(
        f"https://fcm.googleapis.com/v1/projects/{creds['project_id']}/messages:send",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "message": {
                "token": device_token,
                "notification": {"title": title, "body": body},
                "android": {"priority": "NORMAL", "notification": {"channel_id": "lumio_default"}},
            }
        },
    )
    if response.status_code == 200:
        return "ok"
    if response.status_code in (400, 404) and ("UNREGISTERED" in response.text or "INVALID_ARGUMENT" in response.text):
        return "invalid"
    logger.warning("FCM ha risposto %s", response.status_code)
    return "error"


async def send_to_user(user_id: uuid.UUID, title: str, body: str) -> int:
    """Invia a tutti i dispositivi dell'utente; ritorna quanti invii sono riusciti."""
    creds = _load()
    if creds is None:
        return 0

    async with async_session_factory() as db:
        await set_rls_current_user(db, user_id)
        tokens = list((await db.scalars(select(PushDevice.token).where(PushDevice.owner_user_id == user_id))).all())
    if not tokens:
        return 0

    sent = 0
    invalid: list[str] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        access_token = await _access_token(client, creds)
        for token in tokens:
            result = await _send_one(client, creds, access_token, token, title, body)
            if result == "ok":
                sent += 1
            elif result == "invalid":
                invalid.append(token)

    if invalid:
        async with async_session_factory() as db:
            await set_rls_current_user(db, user_id)
            await db.execute(
                delete(PushDevice).where(PushDevice.owner_user_id == user_id, PushDevice.token.in_(invalid))
            )
            await db.commit()
    return sent


async def notify_new_transactions(user_id: uuid.UUID, count: int) -> None:
    """Dopo una sync bancaria con movimenti nuovi. Mai bloccante per il chiamante."""
    if count <= 0 or not is_configured():
        return
    try:
        body = "1 nuovo movimento da controllare" if count == 1 else f"{count} nuovi movimenti da controllare"
        await send_to_user(user_id, "Lumio", body)
    except Exception:
        logger.exception("invio push fallito")

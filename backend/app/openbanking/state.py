"""`state` del flusso di autorizzazione (protezione CSRF del callback).

JWT a vita breve (10 minuti) firmato con `SECRET_KEY`, che porta identita' e
connessione piu' un nonce MONOUSO: la sua impronta SHA-256 e' salvata sulla
riga `bank_connections` e azzerata quando il callback la consuma, cosi' uno
`state` rigiocato non trova piu' nulla. Stesso schema dell'OAuth Google.
"""
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.keys import derive_key
from app.core.security import JWT_ALGORITHM

_PURPOSE = "open_banking_state"
_TTL_MINUTES = 10


def _signing_key() -> str:
    # Chiave dedicata (HKDF): un token di accesso firmato con `SECRET_KEY` non
    # verifica qui e uno `state` non verifica come token di accesso, anche se
    # un giorno mancasse il controllo su `purpose`.
    return derive_key(_PURPOSE).hex()


@dataclass
class DecodedState:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    connection_id: uuid.UUID
    nonce: str


def hash_nonce(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def build_state(workspace_id: uuid.UUID, user_id: uuid.UUID, connection_id: uuid.UUID, nonce: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "purpose": _PURPOSE,
        "workspace_id": str(workspace_id),
        "user_id": str(user_id),
        "connection_id": str(connection_id),
        "nonce": nonce,
        "iat": now,
        "exp": now + timedelta(minutes=_TTL_MINUTES),
    }
    return jwt.encode(payload, _signing_key(), algorithm=JWT_ALGORITHM)


def decode_state(state: str) -> DecodedState | None:
    """`None` se non valido/scaduto/di altro scopo (mai un'eccezione: e' un 400 normale)."""
    try:
        payload = jwt.decode(state, _signing_key(), algorithms=[JWT_ALGORITHM], options={"require": ["exp", "iat"]})
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _PURPOSE:
        return None
    try:
        return DecodedState(
            workspace_id=uuid.UUID(payload["workspace_id"]),
            user_id=uuid.UUID(payload["user_id"]),
            connection_id=uuid.UUID(payload["connection_id"]),
            nonce=str(payload["nonce"]),
        )
    except (KeyError, ValueError):
        return None

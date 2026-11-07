"""`state` del flusso di autorizzazione (protezione CSRF del callback).

Token Fernet (cifrato E autenticato) a vita breve (10 minuti), con chiave
dedicata derivata da `SECRET_KEY` (`core/keys.py`). Porta identita' e connessione
piu' un nonce MONOUSO: la sua impronta SHA-256 e' salvata sulla riga
`bank_connections` e azzerata in modo atomico dal callback, cosi' uno `state`
rigiocato non trova piu' nulla.

Il contenuto e' CIFRATO: la banca e il provider ricevono lo `state` e lo
rimandano indietro, ma non vedono gli identificativi interni (utente,
workspace). Non e' un JWT: non puo' mai essere scambiato con un token di accesso.
"""
import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from app.core.keys import derive_key

_PURPOSE = "open_banking_state"
_TTL_SECONDS = 10 * 60


@dataclass
class DecodedState:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    connection_id: uuid.UUID
    nonce: str


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(derive_key(_PURPOSE)))


def hash_nonce(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def build_state(workspace_id: uuid.UUID, user_id: uuid.UUID, connection_id: uuid.UUID, nonce: str) -> str:
    payload = {
        "purpose": _PURPOSE,
        "workspace_id": str(workspace_id),
        "user_id": str(user_id),
        "connection_id": str(connection_id),
        "nonce": nonce,
    }
    return _fernet().encrypt(json.dumps(payload).encode()).decode()


def decode_state(state: str) -> DecodedState | None:
    """`None` se non valido/scaduto/di altro scopo (mai un'eccezione: e' un 400 normale)."""
    try:
        raw = _fernet().decrypt(state.encode(), ttl=_TTL_SECONDS)
        payload = json.loads(raw)
    except (InvalidToken, ValueError, UnicodeError):
        return None
    if not isinstance(payload, dict) or payload.get("purpose") != _PURPOSE:
        return None
    try:
        return DecodedState(
            workspace_id=uuid.UUID(payload["workspace_id"]),
            user_id=uuid.UUID(payload["user_id"]),
            connection_id=uuid.UUID(payload["connection_id"]),
            nonce=str(payload["nonce"]),
        )
    except (KeyError, ValueError, TypeError):
        return None

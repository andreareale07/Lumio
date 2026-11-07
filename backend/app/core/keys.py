"""Chiavi derivate da `SECRET_KEY`, una per scopo.

Usare lo stesso valore grezzo per firmare JWT, firmare lo `state` OAuth e
cifrare i segreti a riposo significa che una debolezza in uno scopo vale per
tutti. HKDF-SHA256 con un contesto diverso per scopo produce chiavi
indipendenti: un token firmato per uno scopo non e' mai valido per un altro.
I JWT di accesso restano sul valore grezzo (cambiarli invaliderebbe le sessioni
aperte); gli scopi nuovi usano sempre `derive_key`.
"""
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings


def derive_key(purpose: str) -> bytes:
    """32 byte deterministici per `purpose`, derivati da `SECRET_KEY`."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"lumio:{purpose}".encode(),
    ).derive(get_settings().secret_key.encode())

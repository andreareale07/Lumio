"""Cifratura a riposo delle API key AI (SPEC §27, CLAUDE.md "API key/secret
cifrati a riposo"). Chiave Fernet derivata da `SECRET_KEY` via SHA-256 (non
un secret separato da gestire/ruotare: coerente con l'uso gia' fatto di
`secret_key` per firmare i JWT in `app/core/security.py`). Fernet e'
simmetrica e sufficiente qui: l'app deve poter decifrare la chiave per
chiamare il provider, quindi un hash one-way (come per le password) non e'
applicabile.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None

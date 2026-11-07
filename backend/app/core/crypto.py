"""Cifratura a riposo delle API key AI e dei segreti Open Banking (SPEC §27,
CLAUDE.md "API key/secret cifrati a riposo"). Fernet e' simmetrica e
sufficiente qui: l'app deve poter decifrare il segreto per chiamare il
provider, quindi un hash one-way (come per le password) non e' applicabile.

Chiave: HKDF da `SECRET_KEY` con contesto dedicato (`core/keys.py`), cosi' la
cifratura non condivide la chiave con la firma dei JWT. Il formato storico
(SHA-256 semplice di `SECRET_KEY`) resta accettato in LETTURA: i segreti gia'
salvati si decifrano ancora e vengono riscritti col formato nuovo alla prima
modifica. `MultiFernet` cifra sempre con la prima chiave.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings
from app.core.keys import derive_key


def _fernet() -> MultiFernet:
    current = Fernet(base64.urlsafe_b64encode(derive_key("fernet")))
    legacy_digest = hashlib.sha256(get_settings().secret_key.encode()).digest()
    legacy = Fernet(base64.urlsafe_b64encode(legacy_digest))
    return MultiFernet([current, legacy])


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None

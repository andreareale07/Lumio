"""2FA TOTP (RFC 6238): generazione segreto, verifica codice con anti-replay."""
import pyotp

from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.redis import redis_client
from app.models.user import User

# Tolleranza di +-1 intervallo (30s): assorbe lo scarto di orologio del telefono.
_VALID_WINDOW = 1
_REPLAY_TTL_SECONDS = 90


def new_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    return encrypt_secret(secret)


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=get_settings().app_name)


async def verify_code(user: User, code: str) -> bool:
    """Vero se `code` e' valido per il segreto salvato E non e' gia' stato usato
    di recente (un codice intercettato non si puo' riusare nella sua finestra)."""
    if not user.totp_secret_encrypted:
        return False
    secret = decrypt_secret(user.totp_secret_encrypted)
    code = code.strip().replace(" ", "")
    if secret is None or not code.isdigit():
        return False
    if not pyotp.TOTP(secret).verify(code, valid_window=_VALID_WINDOW):
        return False
    first_use = await redis_client.set(f"totp_used:{user.id}:{code}", "1", ex=_REPLAY_TTL_SECONDS, nx=True)
    return bool(first_use)

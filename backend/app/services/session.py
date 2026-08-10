import secrets
import uuid

from app.core.config import get_settings
from app.core.redis import redis_client

_REDIS_KEY_PREFIX = "refresh_token:"


def _redis_key(token: str) -> str:
    return f"{_REDIS_KEY_PREFIX}{token}"


async def create_refresh_token(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    ttl_seconds = get_settings().refresh_token_ttl_days * 24 * 60 * 60
    await redis_client.set(_redis_key(token), str(user_id), ex=ttl_seconds)
    return token


async def get_user_id_for_refresh_token(token: str) -> uuid.UUID | None:
    raw = await redis_client.get(_redis_key(token))
    if raw is None:
        return None
    try:
        return uuid.UUID(raw.decode())
    except ValueError:
        return None


async def revoke_refresh_token(token: str) -> None:
    await redis_client.delete(_redis_key(token))

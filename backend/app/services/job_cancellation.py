"""Richiesta di interruzione di un job in corso (classificazione AI, riclassificazione).

Interruzione COOPERATIVA: l'API imposta un segnale su Redis e il job lo
controlla tra una transazione e l'altra, fermandosi da solo. Niente abort
forzato di arq: ucciderebbe il job a meta' di una scrittura, mentre qui tutto
cio' che e' gia' stato classificato resta classificato e lo stato finale e'
coerente. Il segnale scade da solo (`_TTL_SECONDS`): se il job termina prima di
leggerlo non deve poter interrompere l'esecuzione successiva; per lo stesso
motivo il job lo azzera sia all'avvio sia all'uscita.
"""
import uuid

from app.core.redis import redis_client

_TTL_SECONDS = 600


def _key(kind: str, topic_id: uuid.UUID) -> str:
    return f"cancel:{kind}:{topic_id}"


async def request_cancel(kind: str, topic_id: uuid.UUID) -> None:
    await redis_client.set(_key(kind, topic_id), "1", ex=_TTL_SECONDS)


async def is_cancel_requested(kind: str, topic_id: uuid.UUID) -> bool:
    return bool(await redis_client.get(_key(kind, topic_id)))


async def clear_cancel(kind: str, topic_id: uuid.UUID) -> None:
    await redis_client.delete(_key(kind, topic_id))

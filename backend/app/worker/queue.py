"""Connessione arq lato produttore (l'API accoda, il worker consuma).

Il pool va creato una sola volta e riusato: `arq.connections.create_pool`
apre una connessione Redis, farlo per ogni richiesta sarebbe uno spreco.
Nessun lock/lru_cache serve qui perche' l'inizializzazione e' idempotente a
sufficienza per lo scopo (nel peggiore dei casi, due richieste concorrenti al
primissimo avvio creano il pool due volte; il secondo sovrascrive il primo,
che viene garbage-collected).
"""
import uuid

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings

_pool: ArqRedis | None = None

IMPORT_JOB_FUNCTION = "import_job"


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_import_job(import_id: uuid.UUID, created_by_user_id: uuid.UUID) -> str:
    """Accoda il job di import. `_job_id` fissato su `import_id` rende
    l'accodamento idempotente lato arq: un secondo tentativo di confirm sullo
    stesso import (es. doppio click) mentre il primo job e' ancora in coda o
    in esecuzione non crea un secondo job — arq restituisce `None` invece di
    un nuovo `Job`, che qui trattiamo come "gia' in coda".
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        IMPORT_JOB_FUNCTION,
        str(import_id),
        str(created_by_user_id),
        _job_id=f"import:{import_id}",
    )
    job_id = job.job_id if job is not None else f"import:{import_id}"
    return job_id

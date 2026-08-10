from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.worker.jobs.import_csv import import_csv_job

setup_logging()

_settings = get_settings()


async def startup(ctx) -> None:
    pass


async def shutdown(ctx) -> None:
    pass


class WorkerSettings:
    functions = [import_csv_job]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    job_timeout = _settings.import_job_timeout_seconds
    max_tries = 2
    on_startup = startup
    on_shutdown = shutdown
    # I job supportano l'abort esplicito (POST /imports/{id}/cancel):
    # richiede allow_abort_jobs=True lato worker per honourare il segnale.
    allow_abort_jobs = True

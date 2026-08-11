from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.worker.jobs.import_job import import_job
from app.worker.jobs.market_data import refresh_market_data_for_workspace, refresh_market_data_job
from app.worker.jobs.snapshot import snapshot_job, write_snapshot_for_workspace

setup_logging()

_settings = get_settings()


async def startup(ctx) -> None:
    pass


async def shutdown(ctx) -> None:
    pass


class WorkerSettings:
    functions = [
        import_job,
        refresh_market_data_job,
        refresh_market_data_for_workspace,
        snapshot_job,
        write_snapshot_for_workspace,
    ]
    # Cron giornaliero (SPEC §38, DoD M09 "storico patrimonio via snapshot,
    # non ricalcolato da zero"): prima il refresh prezzi, un'ora dopo lo
    # snapshot — cosi' lo snapshot del giorno usa prezzi gia' aggiornati
    # invece di quelli residui del giorno precedente. `unique=True`
    # (default arq) evita doppia esecuzione se in futuro il worker viene
    # scalato su piu' repliche.
    cron_jobs = [
        cron(refresh_market_data_job, hour=2, minute=0),
        cron(snapshot_job, hour=3, minute=0),
    ]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    job_timeout = _settings.import_job_timeout_seconds
    max_tries = 2
    on_startup = startup
    on_shutdown = shutdown
    # I job supportano l'abort esplicito (POST /imports/{id}/cancel):
    # richiede allow_abort_jobs=True lato worker per honourare il segnale.
    allow_abort_jobs = True

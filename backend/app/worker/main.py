from arq import cron
from arq.connections import RedisSettings
from arq.worker import func as arq_func

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.worker.jobs.ai_classification_job import classify_import_transactions_job
from app.worker.jobs.google_export_job import google_sheets_export_job
from app.worker.jobs.import_job import import_job
from app.worker.jobs.job_health_job import expire_stale_jobs_job
from app.worker.jobs.market_data import refresh_market_data_for_workspace, refresh_market_data_job
from app.worker.jobs.reclassification_job import reclassify_workspace_job
from app.worker.jobs.snapshot import snapshot_job, write_snapshot_for_workspace
from app.worker.jobs.snapshot_backfill import snapshot_backfill_job

setup_logging()

_settings = get_settings()


async def startup(ctx) -> None:
    pass


async def shutdown(ctx) -> None:
    pass


class WorkerSettings:
    functions = [
        import_job,
        # Timeout proprio, distinto dal `job_timeout` globale sotto (vedi
        # docstring di ai_classification_job.py per il motivo): un
        # `arq.worker.func(..., timeout=...)` sovrascrive il default solo
        # per questa funzione, senza toccare gli altri job registrati qui.
        arq_func(
            classify_import_transactions_job,
            timeout=_settings.ai_classification_job_timeout_seconds,
        ),
        refresh_market_data_job,
        refresh_market_data_for_workspace,
        snapshot_job,
        write_snapshot_for_workspace,
        google_sheets_export_job,
        expire_stale_jobs_job,
        # Timeout proprio (puo' scorrere l'intero storico di un workspace),
        # stesso principio di classify_import_transactions_job sopra.
        arq_func(
            reclassify_workspace_job,
            timeout=_settings.reclassification_job_timeout_seconds,
        ),
        # Storico patrimonio ricostruito (FETTA 3): timeout proprio, ampio
        # come reclassify_workspace_job — dominato dalla fase prezzi (HTTP
        # per ogni asset posseduto + FX all'indietro), non dalla matematica.
        arq_func(
            snapshot_backfill_job,
            timeout=_settings.snapshot_backfill_job_timeout_seconds,
        ),
    ]
    # Cron giornaliero (SPEC §38, DoD M09 "storico patrimonio via snapshot,
    # non ricalcolato da zero"): prima il refresh prezzi, un'ora dopo lo
    # snapshot — cosi' lo snapshot del giorno usa prezzi gia' aggiornati
    # invece di quelli residui del giorno precedente. `unique=True`
    # (default arq) evita doppia esecuzione se in futuro il worker viene
    # scalato su piu' repliche.
    #
    # `expire_stale_jobs_job` gira molto piu' spesso (ogni 2 minuti, tramite
    # il trucco croniter `minute=set(range(0,60,2))`): a differenza degli
    # altri due, non calcola nulla di costoso, fa solo query indicizzate su
    # righe non-terminali — le SOGLIE di quanto tempo deve passare prima di
    # considerare un job morto vivono in `system_settings`, mai qui (vedi
    # app/services/job_health.py), cosi' un cambio di soglia non richiede un
    # riavvio del worker. Solo la CADENZA del controllo stesso resta un
    # valore di codice: cambiarla e' una scelta operativa rara, non un
    # parametro che serve regolare da UI.
    cron_jobs = [
        cron(refresh_market_data_job, hour=2, minute=0),
        cron(snapshot_job, hour=3, minute=0),
        cron(expire_stale_jobs_job, minute=set(range(0, 60, 2))),
    ]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    job_timeout = _settings.import_job_timeout_seconds
    max_tries = 2
    on_startup = startup
    on_shutdown = shutdown
    # I job supportano l'abort esplicito (POST /imports/{id}/cancel):
    # richiede allow_abort_jobs=True lato worker per honourare il segnale.
    allow_abort_jobs = True

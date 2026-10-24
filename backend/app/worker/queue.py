"""Connessione arq lato produttore (l'API accoda, il worker consuma).

Il pool va creato una sola volta e riusato: `arq.connections.create_pool`
apre una connessione Redis, farlo per ogni richiesta sarebbe uno spreco.
Nessun lock/lru_cache serve qui perche' l'inizializzazione e' idempotente a
sufficienza per lo scopo (nel peggiore dei casi, due richieste concorrenti al
primissimo avvio creano il pool due volte; il secondo sovrascrive il primo,
che viene garbage-collected).
"""
import uuid
from datetime import date

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings

_pool: ArqRedis | None = None

IMPORT_JOB_FUNCTION = "import_job"
CLASSIFY_IMPORT_TRANSACTIONS_FUNCTION = "classify_import_transactions_job"
MARKET_DATA_REFRESH_FUNCTION = "refresh_market_data_for_workspace"
SNAPSHOT_REBUILD_FUNCTION = "write_snapshot_for_workspace"
GOOGLE_SHEETS_EXPORT_FUNCTION = "google_sheets_export_job"
RECLASSIFICATION_FUNCTION = "reclassify_workspace_job"
SNAPSHOT_BACKFILL_FUNCTION = "snapshot_backfill_job"
POSITIONS_RECOMPUTE_FUNCTION = "positions_recompute_job"


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


async def enqueue_classify_import_job(
    import_id: uuid.UUID, created_by_user_id: uuid.UUID, rerun: bool = False
) -> str:
    """Accoda la classificazione AI disaccoppiata (vedi
    ai_classification_job.py) — stesso principio di `_job_id` fisso di
    `enqueue_import_job`: un solo job di classificazione per import, mai
    duplicato da un retry o da un doppio trigger.

    `rerun=True` (rilancio manuale da Impostazioni > Motore AI): l'id fisso
    NON va usato, arq considera "gia' esistente" un `_job_id` anche quando
    resta solo il RISULTATO di un'esecuzione passata (`keep_result`, 1h) e
    ignorerebbe in silenzio il rilancio — stesso bug gia' documentato per i
    trigger manuali piu' sotto. Il doppio click resta coperto dallo stato
    'pending'/'running' controllato dal chiamante."""
    pool = await get_arq_pool()
    job_id = (
        f"ai_classification:{import_id}:{uuid.uuid4().hex[:8]}" if rerun else f"ai_classification:{import_id}"
    )
    job = await pool.enqueue_job(
        CLASSIFY_IMPORT_TRANSACTIONS_FUNCTION,
        str(import_id),
        str(created_by_user_id),
        _job_id=job_id,
    )
    return job.job_id if job is not None else job_id


async def enqueue_market_data_refresh(workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Trigger manuale (`POST /market-data/refresh`, SPEC §38).

    NESSUN `_job_id` fissato sul workspace (a differenza di
    `enqueue_import_job`, dove e' corretto: `import_id` e' generato una
    volta sola per import). Bug reale trovato testando dal vivo: arq
    considera "gia' esistente" un `_job_id` anche quando esiste solo il
    RISULTATO di un'esecuzione passata ([arq/connections.py] `enqueue_job`,
    `pipe.exists(job_key, result_key_prefix + job_id)`), e il risultato resta
    in Redis per `keep_result` (default 1h). Con un id fisso per workspace,
    ogni click dopo il primo refresh riuscito veniva silenziosamente
    ignorato da arq per un'ora — l'endpoint restituiva comunque 202 (non
    distingue "job accodato" da "arq l'ha scartato"), quindi il tasto
    sembrava funzionare ma non succedeva piu' nulla. Il doppio-click
    "mentre e' in corso" e' gestito ora a livello applicativo controllando
    lo stato in `job_runs` (vedi il router), non da arq."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(MARKET_DATA_REFRESH_FUNCTION, str(workspace_id), str(user_id))
    return job.job_id if job is not None else ""


async def enqueue_snapshot_rebuild(workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Trigger manuale (`POST /portfolio/snapshots/rebuild`, DoD M09) —
    stesso principio/bugfix di `enqueue_market_data_refresh`."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(SNAPSHOT_REBUILD_FUNCTION, str(workspace_id), str(user_id))
    return job.job_id if job is not None else ""


async def enqueue_reclassification(workspace_id: uuid.UUID, user_id: uuid.UUID, scope: str, run_ai: bool) -> str:
    """Trigger manuale (`POST /classification/reclassify`, rework pipeline).

    NESSUN `_job_id` fisso sul workspace — stesso bugfix gia' documentato
    due volte sopra (`enqueue_market_data_refresh`,
    `enqueue_google_sheets_export`): arq considera "gia' esistente" un
    `_job_id` anche quando esiste solo il RISULTATO di un'esecuzione
    passata, che resta in Redis per `keep_result` (default 1h) — con un id
    fisso, ogni riclassificazione dopo la prima riuscita verrebbe
    silenziosamente ignorata da arq per un'ora, mentre l'endpoint
    continuerebbe a rispondere 202. Il doppio-click "mentre e' in corso"
    resta gestito a livello applicativo controllando lo stato in
    `job_runs` (vedi il router), non serve l'idempotenza di arq per quello.
    """
    pool = await get_arq_pool()
    job = await pool.enqueue_job(RECLASSIFICATION_FUNCTION, str(workspace_id), str(user_id), scope, run_ai)
    return job.job_id if job is not None else ""


async def enqueue_snapshot_backfill(
    workspace_id: uuid.UUID, user_id: uuid.UUID, date_from: date | None = None
) -> str:
    """Trigger del backfill storico patrimonio (FETTA 3) — automatico a fine
    import (`worker/jobs/import_job.py`, `api/v1/imports.py`, scoped a
    `date_from=import_row.period_start`) e manuale
    (`POST /portfolios/snapshots/backfill`, `date_from=None` = "ricostruisci
    tutto lo storico").

    NESSUN `_job_id` fisso — stesso bugfix gia' documentato tre volte sopra
    (`enqueue_market_data_refresh`/`enqueue_reclassification`/
    `enqueue_google_sheets_export`): arq considera "gia' esistente" un
    `_job_id` anche quando esiste solo il RISULTATO di un'esecuzione
    passata, che resta in Redis per `keep_result` (default 1h) — con un id
    fisso, un secondo import completato entro un'ora dal primo backfill
    riuscito verrebbe silenziosamente ignorato da arq, lasciando lo storico
    del secondo import mai ricostruito mentre l'endpoint continuerebbe a
    rispondere 202. Il doppio scatto (bottone premuto due volte, o
    automatico+manuale in rapida successione) resta gestito a livello
    applicativo controllando lo stato in `job_runs` (vedi il router), non
    serve l'idempotenza di arq per quello."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        SNAPSHOT_BACKFILL_FUNCTION,
        str(workspace_id),
        str(user_id),
        date_from.isoformat() if date_from is not None else None,
    )
    return job.job_id if job is not None else ""


async def enqueue_google_sheets_export(workspace_id: uuid.UUID, user_id: uuid.UUID, options: dict) -> str:
    """Trigger manuale (`POST /integrations/google/export`, milestone 10).

    NESSUN `_job_id` fisso — stesso bugfix di `enqueue_market_data_refresh`,
    ripetuto qui per errore e trovato testando dal vivo (identico sintomo:
    dopo il primo export riuscito, ogni "Esporta" successivo restituiva 202
    ma non aggiornava piu' lo spreadsheet). Un `_job_id` fisso per workspace
    NON e' innocuo nemmeno se il job precedente e' gia' concluso con
    successo: arq considera "gia' esistente" un `_job_id` anche quando esiste
    solo il RISULTATO di un'esecuzione passata ([arq/connections.py]
    `enqueue_job`, `pipe.exists(job_key, result_key_prefix + job_id)`), che
    resta in Redis per `keep_result` (default 1h) — non solo mentre e'
    "running". Il doppio-click "mentre e' in corso" resta comunque gestito
    a livello applicativo controllando lo stato in `job_runs` (vedi il
    router), non serve l'idempotenza di arq per quello."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(GOOGLE_SHEETS_EXPORT_FUNCTION, str(workspace_id), str(user_id), options)
    return job.job_id if job is not None else ""


async def enqueue_positions_recompute(workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Trigger manuale (`POST /maintenance/positions-recompute`). Nessun
    `_job_id` fisso: stesso motivo di `enqueue_reclassification` (arq
    ignorerebbe per un'ora ogni esecuzione dopo la prima); il doppio click
    e' gestito controllando `job_runs` nel router."""
    pool = await get_arq_pool()
    job = await pool.enqueue_job(POSITIONS_RECOMPUTE_FUNCTION, str(workspace_id), str(user_id))
    return job.job_id if job is not None else ""

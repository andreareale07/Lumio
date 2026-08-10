"""Job arq che processa un import CSV (milestone 04).

Identita' RLS (regola non negoziabile: l'isolamento a doppio livello deve
reggere anche nel worker, mai `SET ROLE lumio_rls_helper`/BYPASSRLS): il job
non ha una richiesta HTTP ne' un JWT, quindi usa `rls_session` (app/db/rls.py)
con l'identita' dell'utente che ha creato l'import, ricevuta come argomento
invece che riletta da una sessione senza identita' impostata.

Limite noto e accettato in M04: se il processo worker muore a meta' (kill
-9) DOPO aver scritto status='processing' ma PRIMA di completare, l'import
resta bloccato in 'processing' — non esiste ancora un meccanismo di
lease/heartbeat per il recovery automatico. Non e' richiesto dal DoD di
questa milestone (SSE trackability, dedup, niente polling); un futuro job di
manutenzione potrebbe far scadere gli import "processing" da troppo tempo.

Limite correlato, scoperto scrivendo i test: se l'identita' con cui gira il
job (created_by_user_id) non e' PIU' membro del workspace, la policy RLS di
SELECT su `imports` (basata sulla stessa `is_workspace_member`) nega anche
la LETTURA della riga, non solo l'eventuale INSERT — quindi il job si ferma
silenziosamente al primo `db.get` (branch "import non trovato") e la riga
resta bloccata a 'queued' invece di transitare a 'failed'. E' una proprieta'
di sicurezza piu' forte (un'identita' non autorizzata non puo' nemmeno
osservare che l'import esiste) ma una proprieta' di liveness piu' debole
(nessuna transizione automatica a uno stato terminale in questo caso). Dato
che oggi l'app non offre alcuna funzionalita' per rimuovere un utente dal
proprio workspace, e' un edge case accettato per M04, non una regressione
rispetto al DoD (SSE, dedup, niente polling) — vedi
test_imports_worker_rls.py per la verifica del comportamento reale.
"""
import logging
import uuid
from datetime import UTC, datetime

from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.services import job_events
from app.services.csv_import import MappingConfig, parse_rows
from app.services.import_paths import original_file_path
from app.storage import get_storage

logger = logging.getLogger("lumio.worker.import_csv")


async def import_csv_job(ctx, import_id: str, created_by_user_id: str) -> None:
    import_uuid = uuid.UUID(import_id)
    user_uuid = uuid.UUID(created_by_user_id)

    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is None:
            logger.warning("import %s not found, skipping", import_id)
            return
        # Guardia di idempotenza: protegge da un retry di arq che ridelivera
        # lo stesso job e da un'eventuale race con POST /imports/{id}/cancel
        # (che imposta status='cancelled' prima che il job parta davvero).
        if import_row.status != "queued":
            logger.info("import %s status=%s (non 'queued'), skip", import_id, import_row.status)
            return
        import_row.status = "processing"
        await db.commit()

    await job_events.emit(import_uuid, "job.started", stage="processing", progress=10)

    try:
        await _process(import_uuid, user_uuid)
    except Exception:
        logger.exception("import %s failed", import_id)
        async with rls_session(user_uuid) as db:
            import_row = await db.get(Import, import_uuid)
            if import_row is not None:
                import_row.status = "failed"
                # Mai contenuto finanziario nel messaggio (SPEC §55): solo
                # una descrizione generica, il dettaglio tecnico resta nei
                # log applicativi (via logger.exception sopra).
                import_row.error_message = "Impossibile completare l'import: errore durante l'elaborazione del file"
                await db.commit()
        await job_events.emit(
            import_uuid, "job.failed", message="Impossibile completare l'import"
        )
        # Non ri-solleva: la gestione dell'errore e' gia' completa (stato
        # persistito + evento emesso). Un retry automatico di arq su un
        # errore di parsing deterministico sarebbe un no-op comunque, per
        # via della guardia sullo stato sopra.


async def _process(import_uuid: uuid.UUID, user_uuid: uuid.UUID) -> None:
    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is None or import_row.status != "processing":
            return  # cancellato/rimosso nel frattempo

        workspace_id = import_row.workspace_id
        financial_account_id = import_row.financial_account_id
        mapping_config = MappingConfig(**import_row.mapping_config)

        raw_bytes = get_storage().read(original_file_path(workspace_id, import_row.id))
        text = raw_bytes.decode(mapping_config.encoding, errors="replace")

        import_row.status = "parsing"
        await db.commit()

    await job_events.emit(import_uuid, "job.progress", stage="parsing", progress=30)
    rows, warnings = parse_rows(text, mapping_config)
    for warning in warnings:
        await job_events.emit(import_uuid, "job.warning", message=warning)
    await job_events.emit(
        import_uuid, "job.progress", stage="parsing", progress=60, transactions_found=len(rows)
    )

    # Insert delle transazioni + aggiornamento import in un'unica transazione
    # DB, un solo commit: e' cio' che rende un eventuale retry sicuro — non
    # esiste stato parzialmente committato da riconciliare (SPEC §58).
    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is None or import_row.status != "parsing":
            return

        for row in rows:
            db.add(
                Transaction(
                    workspace_id=workspace_id,
                    financial_account_id=financial_account_id,
                    import_id=import_row.id,
                    transaction_date=row.transaction_date,
                    value_date=row.value_date,
                    description_raw=row.description_raw,
                    description_normalized=row.description_normalized,
                    reference=row.reference,
                    amount=row.amount,
                    currency=row.currency,
                    direction=row.direction,
                    transaction_type=row.transaction_type,
                    balance_after=row.balance_after,
                    category_id=None,
                )
            )

        import_row.status = "completed"
        import_row.transactions_found = len(rows)
        import_row.transactions_imported = len(rows)
        if rows:
            dates = [r.transaction_date for r in rows]
            import_row.period_start = min(dates)
            import_row.period_end = max(dates)
        import_row.completed_at = datetime.now(UTC)
        await db.commit()

    await job_events.emit(
        import_uuid,
        "job.completed",
        stage="completed",
        progress=100,
        transactions_imported=len(rows),
    )

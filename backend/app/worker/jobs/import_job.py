"""Job arq che processa un import (milestone 04: canale CSV; milestone 05:
canale PDF, dispatch su `Import.file_type`).

Identita' RLS (regola non negoziabile: l'isolamento a doppio livello deve
reggere anche nel worker, mai `SET ROLE lumio_rls_helper`/BYPASSRLS): il job
non ha una richiesta HTTP ne' un JWT, quindi usa `rls_session` (app/db/rls.py)
con l'identita' dell'utente che ha creato l'import, ricevuta come argomento
invece che riletta da una sessione senza identita' impostata.

Limite noto e accettato in M04 (vale anche per il canale PDF): se il processo
worker muore a meta' (kill -9) DOPO aver scritto status='processing' ma PRIMA
di completare, l'import resta bloccato in 'processing' — non esiste ancora un
meccanismo di lease/heartbeat per il recovery automatico. Non e' richiesto dal
DoD di M04 ne' di M05; un futuro job di manutenzione potrebbe far scadere gli
import "processing" da troppo tempo.

Limite correlato, scoperto scrivendo i test M04: se l'identita' con cui gira
il job (created_by_user_id) non e' PIU' membro del workspace, la policy RLS
di SELECT su `imports` (basata sulla stessa `is_workspace_member`) nega anche
la LETTURA della riga, non solo l'eventuale INSERT — quindi il job si ferma
silenziosamente al primo `db.get` (branch "import non trovato") e la riga
resta bloccata a 'queued' invece di transitare a 'failed'. E' una proprieta'
di sicurezza piu' forte (un'identita' non autorizzata non puo' nemmeno
osservare che l'import esiste) ma una proprieta' di liveness piu' debole
(nessuna transizione automatica a uno stato terminale in questo caso). Dato
che oggi l'app non offre alcuna funzionalita' per rimuovere un utente dal
proprio workspace, e' un edge case accettato, non una regressione rispetto al
DoD — vedi test_imports_worker_rls.py per la verifica del comportamento reale.
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.rls import rls_session
from app.models.bank_parser import BankParser as BankParserRow
from app.models.import_ import Import
from app.models.transaction_review_item import TransactionReviewItem
from app.parsers import get_parser
from app.services import job_events
from app.services.ai_classification_trigger import prepare_ai_classification_trigger
from app.services.audit_log_service import log_event
from app.services.classification_loader import load_pipeline_context
from app.services.csv_import import MappingConfig, ParsedRow, parse_rows
from app.services.import_paths import original_file_path
from app.services.system_settings_service import get_setting_value
from app.services.transaction_dedup import RowDedupOutcome, run_transaction_dedup
from app.services.transaction_persistence import finalize_prepared_transactions, prepare_transaction_row
from app.services.transaction_type_mapping_service import resolve_transaction_type
from app.services.transfer_recognition import is_internal_transfer
from app.storage import get_storage
from app.worker.queue import enqueue_classify_import_job

logger = logging.getLogger("lumio.worker.import_job")

_NEEDS_REVIEW_THRESHOLD_KEY = "classification.needs_review_threshold"


async def import_job(ctx, import_id: str, created_by_user_id: str) -> None:
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
        file_type = import_row.file_type
        await db.commit()

    await job_events.emit(import_uuid, "job.started", stage="processing", progress=10)

    try:
        if file_type == "pdf":
            await _process_pdf(import_uuid, user_uuid)
        else:
            await _process_csv(import_uuid, user_uuid)
    except (Exception, asyncio.CancelledError) as exc:
        # Bug reale scoperto su dati veri (import PDF con molte righe da
        # classificare via AI locale, ~14s a chiamata): il budget totale del
        # job (import_job_timeout_seconds, arq `job_timeout`) puo' esaurirsi
        # per il CUMULO delle chiamate, anche se ciascuna singola chiamata
        # resta sotto il proprio timeout (ai_classify_timeout_seconds). Arq
        # a quel punto CANCELLA il task — e da Python 3.8 in poi
        # `asyncio.CancelledError` eredita da BaseException, NON da
        # Exception: un `except Exception:` (com'era prima) lo lascia
        # passare senza eseguire nessuna pulizia, lasciando la riga import
        # bloccata per sempre nello stato intermedio in cui si trovava
        # (mai "failed", nessun bottone di eliminazione utilizzabile perche'
        # la guardia di DELETE /imports/{id} blocca proprio gli stati non
        # terminali). Va quindi catturata esplicitamente qui.
        is_cancelled = isinstance(exc, asyncio.CancelledError)
        logger.exception("import %s failed%s", import_id, " (cancellato per timeout)" if is_cancelled else "")
        async with rls_session(user_uuid) as db:
            import_row = await db.get(Import, import_uuid)
            if import_row is not None:
                import_row.status = "failed"
                # Mai contenuto finanziario nel messaggio (SPEC §55): solo
                # una descrizione generica, il dettaglio tecnico resta nei
                # log applicativi (via logger.exception sopra).
                import_row.error_message = (
                    "Impossibile completare l'import: tempo massimo di elaborazione superato"
                    if is_cancelled
                    else "Impossibile completare l'import: errore durante l'elaborazione del file"
                )
                await db.commit()
        await job_events.emit(
            import_uuid, "job.failed", message="Impossibile completare l'import"
        )
        if is_cancelled:
            # MAI assorbire una cancellazione reale: arq deve continuare a
            # vedere il timeout come tale (per le sue metriche/log propri) —
            # qui si e' solo garantito che la pulizia applicativa avvenga
            # PRIMA che la cancellazione risalga, non che venga ignorata.
            raise
        # Per un errore "normale" (non cancellazione) non si ri-solleva: la
        # gestione e' gia' completa (stato persistito + evento emesso). Un
        # retry automatico di arq su un errore di parsing deterministico
        # sarebbe un no-op comunque, per via della guardia sullo stato sopra.


async def _process_csv(import_uuid: uuid.UUID, user_uuid: uuid.UUID) -> None:
    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is None or import_row.status != "processing":
            return  # cancellato/rimosso nel frattempo

        workspace_id = import_row.workspace_id
        financial_account_id = import_row.financial_account_id
        mapping_config = MappingConfig(**import_row.mapping_config)

        raw_bytes = get_storage().read(original_file_path(workspace_id, import_row.id, "csv"))
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

    await _insert_transactions_and_complete(import_uuid, user_uuid, workspace_id, financial_account_id, rows)


async def _process_pdf(import_uuid: uuid.UUID, user_uuid: uuid.UUID) -> None:
    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is None or import_row.status != "processing":
            return

        workspace_id = import_row.workspace_id
        financial_account_id = import_row.financial_account_id
        bank_parser_row = await db.get(BankParserRow, import_row.bank_parser_id)
        # bank_parser_id e' stato risolto e salvato all'upload (vedi
        # app/api/v1/imports.py:_detect_bank_parser) — qui si ripercorre solo
        # il registro per ottenere l'implementazione concreta, senza ripetere
        # la detection.
        parser = get_parser(bank_parser_row.parser_type)
        parser_type = bank_parser_row.parser_type

        raw_bytes = get_storage().read(original_file_path(workspace_id, import_row.id, "pdf"))

        import_row.status = "parsing"
        await db.commit()

    await job_events.emit(import_uuid, "job.progress", stage="parsing", progress=30)

    # SPEC §53 (timeout): l'apertura superficiale gia' avvenuta all'upload
    # (upload_validation._validate_pdf_structure) non garantisce che
    # l'estrazione COMPLETA di tutte le pagine sia comunque veloce — un PDF
    # con moltissime pagine/tabelle potrebbe restare oltre un limite
    # ragionevole. Qui il costo e' asincrono (job, non richiesta HTTP) ma
    # deve comunque avere un limite: senza, un worker slot resterebbe
    # bloccato indefinitamente su un singolo import patologico.
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(parser.parse, raw_bytes),
            timeout=get_settings().import_pdf_parse_timeout_seconds,
        )
    except TimeoutError as exc:
        raise RuntimeError("timeout durante il parsing del PDF") from exc

    for warning in result.warnings:
        await job_events.emit(import_uuid, "job.warning", message=warning)
    await job_events.emit(
        import_uuid, "job.progress", stage="parsing", progress=60, transactions_found=len(result.rows)
    )

    # Milestone 09.5b: riconoscimento dei trasferimenti interni (SPEC §37) —
    # PRIMA dell'override per etichetta di M09.5 sotto, cosi' l'utente puo'
    # sempre forzare un comportamento diverso se questa euristica sbaglia.
    # Capability opzionale del parser (None per un parser che non la
    # supporta, o per una riga che non e' un bonifico riconoscibile).
    # Rework pipeline: la controparte (nome/IBAN) viene ora PERSISTITA sulla
    # riga invece di essere scartata dopo il solo check di
    # is_internal_transfer — per un bonifico e' spesso l'unico segnale
    # utile di "chi" (diventa il merchant quando la descrizione da sola non
    # produce nulla, vedi sotto) e rende `reapply_internal_transfer_
    # detection` indipendente dal dover ri-parsare la descrizione col
    # parser originale.
    async with rls_session(user_uuid) as db:
        for row in result.rows:
            counterparty = parser.extract_transfer_counterparty(row.description_raw)
            if counterparty is not None:
                row.counterparty_name = counterparty.name
                row.counterparty_iban = counterparty.iban
                if await is_internal_transfer(db, workspace_id, counterparty):
                    row.transaction_type = "transfer"

    # Milestone 09.5: il default del parser (gia' in row.transaction_type)
    # resta il fallback — qui si sovrascrive solo se l'utente ha salvato un
    # override per questa etichetta di QUESTO parser, in QUESTO workspace.
    async with rls_session(user_uuid) as db:
        for row in result.rows:
            row.transaction_type = await resolve_transaction_type(
                db, workspace_id, parser_type, row.source_type_raw, row.transaction_type
            )

    await _insert_transactions_and_complete(
        import_uuid, user_uuid, workspace_id, financial_account_id, result.rows
    )


def _build_review_item(
    workspace_id: uuid.UUID,
    import_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    outcome: RowDedupOutcome,
    row: ParsedRow,
    *,
    status: str,
    auto_resolved: bool = False,
    decided_at: datetime | None = None,
) -> TransactionReviewItem:
    return TransactionReviewItem(
        workspace_id=workspace_id,
        import_id=import_id,
        financial_account_id=financial_account_id,
        row_index=outcome.index,
        transaction_date=row.transaction_date,
        value_date=row.value_date,
        description_raw=row.description_raw,
        description_normalized=row.description_normalized,
        amount=row.amount,
        currency=row.currency,
        direction=row.direction,
        transaction_type=row.transaction_type,
        source_type_raw=row.source_type_raw,
        reference=row.reference,
        balance_after=row.balance_after,
        counterparty_name=row.counterparty_name,
        counterparty_iban=row.counterparty_iban,
        new_fingerprint=outcome.fingerprint,
        candidate_existing_transaction_id=outcome.candidate_existing_transaction_id,
        status=status,
        auto_resolved=auto_resolved,
        dedup_decision_id=outcome.dedup_decision_id,
        decided_at=decided_at,
    )


async def _insert_transactions_and_complete(
    import_uuid: uuid.UUID,
    user_uuid: uuid.UUID,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    rows: list[ParsedRow],
) -> None:
    # Insert delle transazioni + aggiornamento import in un'unica transazione
    # DB, un solo commit: e' cio' che rende un eventuale retry sicuro — non
    # esiste stato parzialmente committato da riconciliare (SPEC §58).
    # Condivisa tra canale csv e pdf: entrambi convergono sulla stessa forma
    # intermedia (ParsedRow) prima di toccare `transactions`.
    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is None or import_row.status != "parsing":
            return

        # Pipeline di classificazione deterministica (regole utente -> tipo
        # transazione, vedi app/services/classification_pipeline.py),
        # valutata qui, inline: e' locale e rapida. La classificazione AI
        # (SPEC §28: Rules -> AI) NON avviene piu' qui — bug reale scoperto
        # sui dati veri dell'utente: il timeout del job di import e' un
        # budget cumulativo su TUTTO il job (arq `job_timeout`), non per
        # singola chiamata AI, quindi un import con molte righe non
        # classificate deterministicamente poteva essere cancellato a meta'
        # solo per il tempo totale speso a interrogare il provider in
        # sequenza. Le righe non classificate qui vengono lasciate
        # `category_id IS NULL` e classificate DOPO, da un job separato con
        # un proprio timeout (vedi ai_classification_job.py) — l'import
        # stesso non aspetta piu' l'AI per completarsi.
        pipeline_ctx = await load_pipeline_context(db, workspace_id)
        needs_review_threshold = float(await get_setting_value(_NEEDS_REVIEW_THRESHOLD_KEY, 0.6))

        # Transaction Deduplication Engine (docs/SPEC_DEDUP_TRANSACTION.md):
        # gira PRIMA di qualunque side-effect per riga. Una riga DUPLICATE
        # non deve mai essere classificata ne' generare un
        # InvestmentTransaction (SPEC §20); una riga REVIEW non deve
        # generare nulla finche' l'utente non decide (SPEC §14: mai un
        # "automatic duplicate" su un match incerto, ma nemmeno un insert
        # automatico).
        dedup_result = await run_transaction_dedup(db, workspace_id, financial_account_id, rows)

        now = datetime.now(UTC)
        prepared = []
        auto_new_links = []

        for outcome in dedup_result.outcomes:
            row = rows[outcome.index]

            if outcome.outcome == "review":
                db.add(
                    _build_review_item(
                        workspace_id, import_row.id, financial_account_id, outcome, row, status="pending"
                    )
                )
                continue

            review_item = None
            if outcome.auto_resolved:
                # Una TransactionDedupDecision precedente (SPEC §17) risolve
                # questo caso senza chiedere di nuovo — persistito comunque
                # come TransactionReviewItem gia' risolto, per audit (SPEC
                # §33): resta l'esito di una decisione umana, solo applicata
                # automaticamente a un caso equivalente.
                review_item = _build_review_item(
                    workspace_id,
                    import_row.id,
                    financial_account_id,
                    outcome,
                    row,
                    status="confirmed_new" if outcome.outcome == "new" else "confirmed_duplicate",
                    auto_resolved=True,
                    decided_at=now,
                )
                db.add(review_item)

            if outcome.outcome == "new":
                prepared_row = prepare_transaction_row(
                    pipeline_ctx,
                    workspace_id=workspace_id,
                    financial_account_id=financial_account_id,
                    import_id=import_row.id,
                    row=row,
                    needs_review_threshold=needs_review_threshold,
                )
                prepared.append(prepared_row)
                if review_item is not None:
                    auto_new_links.append((review_item, prepared_row))
            # outcome.outcome == "duplicate": nessun'altra azione oltre
            # all'eventuale review_item di audit gia' aggiunto sopra.

        await finalize_prepared_transactions(db, workspace_id, financial_account_id, prepared)
        for review_item, prepared_row in auto_new_links:
            review_item.resolved_transaction_id = prepared_row.transaction.id

        import_row.transactions_found = len(rows)
        import_row.transactions_imported = dedup_result.new_count
        import_row.transactions_duplicate = dedup_result.duplicate_count
        import_row.transactions_review_pending = dedup_result.review_count
        if rows:
            dates = [r.transaction_date for r in rows]
            import_row.period_start = min(dates)
            import_row.period_end = max(dates)
        import_row.completed_at = now

        should_enqueue_ai_job = False
        if dedup_result.review_count > 0:
            # SPEC §19: non dichiarare "completed" se restano decisioni
            # obbligatorie — stato dedicato gia' previsto dal CHECK
            # constraint di Import.status (vedi migration 0004/0033).
            # L'enqueue della classificazione AI resta posticipato a quando
            # l'ultima review viene decisa (POST /imports/{id}/review-items/
            # {item_id}/decision), mai mentre l'import e' in questo stato.
            import_row.status = "ready_for_review"
        else:
            import_row.status = "completed"
            should_enqueue_ai_job = await prepare_ai_classification_trigger(db, workspace_id, import_row)

        await log_event(
            db,
            workspace_id,
            user_uuid,
            "IMPORT_COMPLETED",
            entity_type="import",
            entity_id=import_row.id,
            metadata={
                "transactions_imported": dedup_result.new_count,
                "transactions_duplicate": dedup_result.duplicate_count,
                "transactions_review_pending": dedup_result.review_count,
            },
        )
        await db.commit()

    await job_events.emit(
        import_uuid,
        "job.completed",
        stage="completed",
        progress=100,
        transactions_imported=dedup_result.new_count,
        transactions_duplicate=dedup_result.duplicate_count,
        transactions_review_pending=dedup_result.review_count,
    )

    if should_enqueue_ai_job:
        await enqueue_classify_import_job(import_uuid, user_uuid)

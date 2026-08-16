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
from decimal import Decimal

from app.core.config import get_settings
from app.db.rls import rls_session
from app.models.bank_parser import BankParser as BankParserRow
from app.models.classification import Classification
from app.models.import_ import Import
from app.models.investment_transaction import InvestmentTransaction
from app.models.transaction import Transaction
from app.parsers import get_parser
from app.services import job_events
from app.services.ai_profile_service import get_active_profile
from app.services.asset_matching import get_or_create_asset_by_isin
from app.services.audit_log_service import log_event
from app.services.classification_loader import load_pipeline_context
from app.services.classification_pipeline import ClassifiableRow, classify_deterministic
from app.services.confidence import needs_review as score_needs_review
from app.services.csv_import import MappingConfig, ParsedRow, parse_rows
from app.services.import_paths import original_file_path
from app.services.merchant_extraction import extract_merchant
from app.services.position_service import recompute_position
from app.services.system_classification import is_ai_eligible
from app.services.system_settings_service import get_setting_value
from app.services.trade_parsing import ParsedTrade, parse_trade_description
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
        # un proprio timeout (vedi ai_classification_job.py, accodato in
        # fondo a questa funzione) — l'import stesso non aspetta piu' l'AI
        # per completarsi.
        pipeline_ctx = await load_pipeline_context(db, workspace_id)
        active_ai_profile = await get_active_profile(db, workspace_id)
        needs_review_threshold = float(await get_setting_value(_NEEDS_REVIEW_THRESHOLD_KEY, 0.6))

        transactions: list[Transaction] = []
        matched_categories: dict[int, uuid.UUID] = {}
        matched_methods: dict[int, str] = {}
        matched_scores: dict[int, Decimal] = {}
        matched_explanations: dict[int, str | None] = {}
        # Milestone 09c: se la DESCRIZIONE matcha il formato Trade Republic
        # per i movimenti "Commercio" (verificato sui dati reali dell'utente,
        # vedi docstring di trade_parsing.py), si deriva automaticamente un
        # InvestmentTransaction — indipendente dal canale/parser, il check e'
        # solo sul testo della descrizione.
        parsed_trades: dict[int, ParsedTrade] = {}
        for index, row in enumerate(rows):
            # Rework pipeline: merchant risvegliato (colonna esistente dalla
            # milestone 03, mai valorizzata finora). La controparte di un
            # bonifico (se riconosciuta) VINCE sempre sull'estrazione
            # generica, non il contrario: `extract_merchant` su una
            # descrizione tipo "Outgoing transfer for Luca Bianchi
            # (IT99...)" produce un frammento di frase troncato
            # ("Outgoing Transfer For Luca", i primi 4 token), perche'
            # non riconosce quel formato come rumore da scartare — mentre
            # `counterparty_name` viene da un match strutturato preciso
            # (nome+IBAN tra parentesi) ed e' sempre piu' affidabile quando
            # disponibile. `extract_merchant` resta il fallback per tutto
            # cio' che non e' un bonifico riconosciuto.
            row.merchant = row.counterparty_name or extract_merchant(row.description_raw)

            classifiable_row = ClassifiableRow(
                description_raw=row.description_raw,
                description_normalized=row.description_normalized,
                merchant=row.merchant,
                transaction_type=row.transaction_type,
            )
            outcome = classify_deterministic(pipeline_ctx, classifiable_row)
            matched_category_id = outcome.category_id if outcome is not None else None

            transaction = Transaction(
                workspace_id=workspace_id,
                financial_account_id=financial_account_id,
                import_id=import_row.id,
                transaction_date=row.transaction_date,
                value_date=row.value_date,
                description_raw=row.description_raw,
                description_normalized=row.description_normalized,
                merchant=row.merchant,
                counterparty_name=row.counterparty_name,
                counterparty_iban=row.counterparty_iban,
                reference=row.reference,
                amount=row.amount,
                currency=row.currency,
                direction=row.direction,
                transaction_type=row.transaction_type,
                source_type_raw=row.source_type_raw,
                balance_after=row.balance_after,
                category_id=matched_category_id,
            )
            db.add(transaction)
            transactions.append(transaction)
            if outcome is not None:
                matched_categories[index] = outcome.category_id
                matched_methods[index] = outcome.method
                matched_scores[index] = outcome.score
                matched_explanations[index] = outcome.explanation
                transaction.needs_review = score_needs_review(outcome.score, needs_review_threshold)

            parsed_trade = parse_trade_description(row.description_raw)
            if parsed_trade is not None:
                parsed_trades[index] = parsed_trade

        if matched_categories or parsed_trades:
            # Serve un flush per ottenere gli id (server-generated) delle
            # transazioni appena aggiunte, prima di poterli referenziare da
            # `classifications.transaction_id` — un solo commit resta alla
            # fine della funzione (invariante gia' esistente in M04/M05).
            await db.flush()
            for index, category_id in matched_categories.items():
                db.add(
                    Classification(
                        transaction_id=transactions[index].id,
                        method=matched_methods[index],
                        category_id=category_id,
                        score=matched_scores[index],
                        explanation=matched_explanations[index],
                    )
                )
            # Milestone 09c: un InvestmentTransaction per ogni riga
            # riconosciuta, collegata alla transazione bancaria via
            # `transaction_id` (link opzionale, qui popolato perche' e'
            # esattamente il movimento che ha generato quel cash flow — mai
            # una seconda scrittura di cassa duplicata). Prezzo = importo
            # assoluto / quantita' (commissione spalmata, vedi
            # trade_parsing.py); asset auto-riconosciuto/creato per ISIN.
            touched_assets: dict[uuid.UUID, str] = {}
            for index, trade in parsed_trades.items():
                transaction = transactions[index]
                asset = await get_or_create_asset_by_isin(
                    db, workspace_id, trade.isin, trade.asset_name, transaction.currency
                )
                price = abs(transaction.amount) / trade.quantity
                db.add(
                    InvestmentTransaction(
                        workspace_id=workspace_id,
                        financial_account_id=financial_account_id,
                        asset_id=asset.id,
                        transaction_id=transaction.id,
                        trade_date=transaction.transaction_date,
                        type=trade.type,
                        quantity=trade.quantity,
                        price=price,
                        amount=transaction.amount,
                        currency=transaction.currency,
                        source_type_raw=trade.source_type_raw,
                    )
                )
                touched_assets[asset.id] = transaction.currency

            for asset_id, currency in touched_assets.items():
                await recompute_position(db, workspace_id, financial_account_id, asset_id, currency)

        import_row.status = "completed"
        import_row.transactions_found = len(rows)
        import_row.transactions_imported = len(rows)
        if rows:
            dates = [r.transaction_date for r in rows]
            import_row.period_start = min(dates)
            import_row.period_end = max(dates)
        import_row.completed_at = datetime.now(UTC)

        # Righe non classificate deterministicamente E ammesse all'AI (vedi
        # system_classification.is_ai_eligible): un investimento/
        # trasferimento/dividendo/interesse/tassa/commissione rimasto senza
        # categoria (es. quella attesa e' stata disattivata dall'utente) non
        # va comunque all'AI — la guardia negativa in
        # ai_classification_job.py lo escluderebbe comunque dalla query, ma
        # l'indicatore "x/N" mostrato in UI deve gia' riflettere solo cio'
        # che il job classifichera' davvero, non un conteggio piu' ampio che
        # includerebbe righe mai destinate all'AI.
        unclassified_ai_eligible_count = sum(
            1
            for index in range(len(transactions))
            if index not in matched_categories and is_ai_eligible(rows[index].transaction_type)
        )
        should_enqueue_ai_job = active_ai_profile is not None and unclassified_ai_eligible_count > 0
        import_row.ai_classification_status = "pending" if should_enqueue_ai_job else "skipped"
        import_row.ai_transactions_total = unclassified_ai_eligible_count if should_enqueue_ai_job else 0

        await log_event(
            db,
            workspace_id,
            user_uuid,
            "IMPORT_COMPLETED",
            entity_type="import",
            entity_id=import_row.id,
            metadata={"transactions_imported": len(rows)},
        )
        await db.commit()

    await job_events.emit(
        import_uuid,
        "job.completed",
        stage="completed",
        progress=100,
        transactions_imported=len(rows),
    )

    if should_enqueue_ai_job:
        await enqueue_classify_import_job(import_uuid, user_uuid)

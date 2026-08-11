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

from app.ai.base import AIClassificationResult, ClassifiableTransaction
from app.ai.registry import build_classifier
from app.core.config import get_settings
from app.db.rls import rls_session
from app.models.bank_parser import BankParser as BankParserRow
from app.models.classification import Classification
from app.models.import_ import Import
from app.models.investment_transaction import InvestmentTransaction
from app.models.transaction import Transaction
from app.parsers import get_parser
from app.services import job_events
from app.services.ai_classification import classify_transaction, load_category_options
from app.services.ai_profile_service import get_active_profile
from app.services.asset_matching import get_or_create_asset_by_isin
from app.services.confidence import compute_ai_confidence
from app.services.csv_import import MappingConfig, ParsedRow, parse_rows
from app.services.import_paths import original_file_path
from app.services.position_service import recompute_position
from app.services.rule_loader import load_active_rule_specs
from app.services.rules_engine import Probe, evaluate
from app.services.trade_parsing import ParsedTrade, parse_trade_description
from app.services.transaction_type_mapping_service import resolve_transaction_type
from app.services.transfer_recognition import is_internal_transfer
from app.storage import get_storage

logger = logging.getLogger("lumio.worker.import_job")


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
    async with rls_session(user_uuid) as db:
        for row in result.rows:
            counterparty = parser.extract_transfer_counterparty(row.description_raw)
            if counterparty is not None and await is_internal_transfer(db, workspace_id, counterparty):
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

        # Rules Engine (milestone 06, SPEC §23) valutato prima di qualsiasi
        # AI (milestone 07, SPEC §28: Rules -> AI) — nessun parser popola
        # ancora `merchant`, quindi entrambi matchano solo su description
        # qui, ma i motori restano invariati quando un parser lo popolera'.
        # Le chiamate AI restano sequenziali dentro la stessa transazione
        # DB gia' usata per le regole: accettabile alla scala di un import
        # personale (decine/centinaia di righe), non pensato per volumi
        # enterprise — un provider lento allunga la durata del job ma non
        # blocca richieste HTTP (gia' async via worker, SPEC §51).
        active_rules = await load_active_rule_specs(db, workspace_id)
        active_ai_profile = await get_active_profile(db, workspace_id)
        ai_classifier = build_classifier(active_ai_profile)
        ai_categories = await load_category_options(db, workspace_id) if active_ai_profile is not None else []

        transactions: list[Transaction] = []
        matched_categories: dict[int, uuid.UUID] = {}
        ai_results: dict[int, AIClassificationResult] = {}
        # Milestone 09c: se la DESCRIZIONE matcha il formato Trade Republic
        # per i movimenti "Commercio" (verificato sui dati reali dell'utente,
        # vedi docstring di trade_parsing.py), si deriva automaticamente un
        # InvestmentTransaction — indipendente dal canale/parser, il check e'
        # solo sul testo della descrizione.
        parsed_trades: dict[int, ParsedTrade] = {}
        for index, row in enumerate(rows):
            probe = Probe(
                description_raw=row.description_raw,
                description_normalized=row.description_normalized,
                merchant=None,
            )
            matched_category_id = evaluate(active_rules, probe)
            if matched_category_id is None and ai_categories:
                ai_result = await classify_transaction(
                    ai_classifier,
                    ai_categories,
                    ClassifiableTransaction(
                        description_raw=row.description_raw,
                        description_normalized=row.description_normalized,
                        merchant=None,
                        amount=str(row.amount),
                        currency=row.currency,
                        direction=row.direction,
                    ),
                )
                if ai_result is not None:
                    matched_category_id = ai_result.category_id
                    ai_results[index] = ai_result

            transaction = Transaction(
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
                source_type_raw=row.source_type_raw,
                balance_after=row.balance_after,
                category_id=matched_category_id,
            )
            db.add(transaction)
            transactions.append(transaction)
            if matched_category_id is not None and index not in ai_results:
                matched_categories[index] = matched_category_id

            parsed_trade = parse_trade_description(row.description_raw)
            if parsed_trade is not None:
                parsed_trades[index] = parsed_trade

        if matched_categories or ai_results or parsed_trades:
            # Serve un flush per ottenere gli id (server-generated) delle
            # transazioni appena aggiunte, prima di poterli referenziare da
            # `classifications.transaction_id` — un solo commit resta alla
            # fine della funzione (invariante gia' esistente in M04/M05).
            await db.flush()
            for index, category_id in matched_categories.items():
                db.add(
                    Classification(
                        transaction_id=transactions[index].id,
                        method="rule",
                        category_id=category_id,
                        score=Decimal("1.00"),
                    )
                )
            for index, ai_result in ai_results.items():
                db.add(
                    Classification(
                        transaction_id=transactions[index].id,
                        method="ai",
                        provider=active_ai_profile.provider,
                        model=active_ai_profile.model,
                        category_id=ai_result.category_id,
                        score=compute_ai_confidence(ai_result.raw_confidence, has_merchant=False),
                        explanation=ai_result.explanation,
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
        await db.commit()

    await job_events.emit(
        import_uuid,
        "job.completed",
        stage="completed",
        progress=100,
        transactions_imported=len(rows),
    )

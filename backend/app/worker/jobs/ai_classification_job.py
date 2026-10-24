"""Job arq separato per la classificazione AI delle transazioni di un import
(milestone rework UX/design — disaccoppiamento AI). Bug reale scoperto sui
dati veri dell'utente: prima, la classificazione AI avveniva DENTRO
`import_job.py`, sotto lo stesso `job_timeout` (arq, cumulativo su tutto il
job) usato per il parsing — un import con molte righe non classificate dalle
regole poteva essere cancellato a meta' anche se ogni singola chiamata AI
restava sotto il proprio timeout, perche' il tempo TOTALE speso in sequenza
superava il budget del job di import. Qui la classificazione ha un job (e un
timeout, vedi app/worker/main.py) tutto suo: l'import si considera completo
appena le transazioni sono inserite, e questo job le classifica in
background, aggiornando `imports.ai_transactions_classified` per l'indicatore
"x/N" in UI.

Identita' RLS: stesso pattern di import_job.py, nessuna richiesta HTTP/JWT
disponibile qui.

Ogni step (classificazione di UNA transazione, aggiornamento del contatore)
apre una propria `rls_session` invece di tenerne una sola aperta per tutto il
loop: ogni chiamata al provider AI puo' impiegare secondi, e non ha senso
tenere una connessione/transazione DB aperta e inattiva per tutta la sua
durata — mai un problema di correttezza (ogni oggetto passato attraverso il
confine di sessione e' un valore Python semplice, gia' completamente
caricato, mai un'istanza ORM da cui pendono attributi non caricati).
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.ai.base import CategoryOption, ClassifiableTransaction
from app.ai.registry import build_classifier
from app.core.config import get_settings
from app.db.rls import rls_session
from app.models.classification import Classification
from app.models.financial_account import FinancialAccount
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.services import job_events
from app.services.job_cancellation import clear_cancel, is_cancel_requested
from app.services.ai_run_event_service import (
    MAX_ERROR_EVENTS_PER_RUN,
    PendingEvent,
    record_events,
)
from app.services.ai_classification import classify_transaction, kinds_for_transaction, load_category_options
from app.services.ai_profile_service import get_active_profile
from app.services.confidence import compute_ai_confidence, needs_review as score_needs_review
from app.services.system_classification import AI_EXCLUDED_TRANSACTION_TYPES
from app.services.system_settings_service import get_setting_value

_NEEDS_REVIEW_THRESHOLD_KEY = "classification.needs_review_threshold"

logger = logging.getLogger("lumio.worker.ai_classification_job")

NAMESPACE = "ai_classification"
# Chiave del segnale di interruzione (vedi app/services/job_cancellation.py).
CANCEL_KIND = "ai_classification"

# Oltre questa soglia di fallimenti di PROVIDER consecutivi (connessione
# rifiutata, timeout, risposta non interpretabile — non "il modello non ha
# trovato un match", quello e' un esito legittimo), il job si interrompe
# invece di scorrere l'intera coda sapendo gia' che ogni chiamata fallira'
# comunque. Scoperto testando un'interruzione reale del provider (container
# Ollama spento a meta' import): senza questa soglia il job restava
# 'running' fino al timeout complessivo, fingendo progresso per tutta la
# coda restante.
_MAX_CONSECUTIVE_PROVIDER_ERRORS = 3


class AIProviderUnavailableError(Exception):
    """Sollevata quando il provider AI fallisce per troppe righe consecutive
    di fila — vedi _MAX_CONSECUTIVE_PROVIDER_ERRORS. Catturata dal blocco
    try/except di `classify_import_transactions_job`, che marca il job
    'failed' con un messaggio comprensibile invece del generico
    "Classificazione AI interrotta"."""


async def _flush_events(
    user_uuid: uuid.UUID, workspace_id: uuid.UUID, import_uuid: uuid.UUID, events: list[PendingEvent]
) -> None:
    """Scrive il registro eventi della run in una sessione propria (la
    sessione RLS ha l'identita' solo fino al commit). Un errore qui non deve
    mai far fallire un job che ha gia' fatto il suo lavoro."""
    if not events:
        return
    try:
        async with rls_session(user_uuid) as db:
            await record_events(db, workspace_id, "import_classification", events, import_id=import_uuid)
            await db.commit()
    except Exception:
        logger.exception("scrittura del registro eventi AI fallita (import %s)", import_uuid)


@dataclass
class _UnclassifiedRow:
    id: uuid.UUID
    description_raw: str
    description_normalized: str
    merchant: str | None
    amount: str
    currency: str
    direction: str
    transaction_type: str
    transaction_date: str
    counterparty_name: str | None


def _categories_for_row(all_categories: list[CategoryOption], row: "_UnclassifiedRow") -> list[CategoryOption]:
    """Filtro per kind applicato in Python (rework prompt AI): righe diverse
    nello stesso import possono avere direction/transaction_type diversi,
    quindi il set di kind ammessi si calcola per riga, non una volta sola
    per l'intero import — evita una query DB per riga per ottenere lo stesso
    risultato che una lista gia' in memoria puo' dare."""
    allowed_kinds = kinds_for_transaction(row.direction, row.transaction_type)
    return [c for c in all_categories if c.kind in allowed_kinds]


async def classify_import_transactions_job(ctx, import_id: str, created_by_user_id: str) -> None:
    import_uuid = uuid.UUID(import_id)
    user_uuid = uuid.UUID(created_by_user_id)

    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is None or import_row.ai_classification_status != "pending":
            # Guardia di idempotenza, stesso principio di import_job.py: un
            # retry di arq o un import gia' cancellato/eliminato nel
            # frattempo non deve ripartire da capo o operare su dati che non
            # esistono piu'.
            logger.info(
                "import %s ai_classification_status=%s, skip",
                import_id,
                import_row.ai_classification_status if import_row else None,
            )
            return
        workspace_id = import_row.workspace_id
        financial_account_id = import_row.financial_account_id
        total = import_row.ai_transactions_total
        await clear_cancel(CANCEL_KIND, import_uuid)
        import_row.ai_classification_status = "running"
        await db.commit()

    await job_events.emit(import_uuid, "job.started", namespace=NAMESPACE, processed=0, total=total)

    events: list[PendingEvent] = []
    try:
        cancelled = await _classify_all(import_uuid, user_uuid, workspace_id, total, financial_account_id, events)
    except (Exception, asyncio.CancelledError) as exc:
        # Stesso pattern di import_job.py: asyncio.CancelledError eredita da
        # BaseException (Python 3.8+), un `except Exception:` la lascerebbe
        # passare senza pulizia, lasciando l'import bloccato per sempre in
        # ai_classification_status='running'.
        is_cancelled = isinstance(exc, asyncio.CancelledError)
        logger.exception(
            "classificazione AI import %s fallita%s",
            import_id,
            " (cancellata per timeout)" if is_cancelled else "",
        )
        failure_message = (
            "Provider AI non raggiungibile, classificazione interrotta"
            if isinstance(exc, AIProviderUnavailableError)
            else "Classificazione AI interrotta"
        )
        events.append(
            PendingEvent(
                "error",
                "job_interrupted",
                "provider_unreachable"
                if isinstance(exc, AIProviderUnavailableError)
                else ("cancelled" if is_cancelled else "unexpected"),
            )
        )
        async with rls_session(user_uuid) as db:
            import_row = await db.get(Import, import_uuid)
            if import_row is not None:
                import_row.ai_classification_status = "failed"
                # Persistito (non solo emesso via SSE, effimero): l'utente
                # deve poter capire perche' e' fallita anche dopo un
                # refresh pagina o se non stava guardando la UI in quel
                # momento — gap reale scoperto testando un'interruzione del
                # provider AI dal vivo.
                import_row.ai_classification_error_message = failure_message
                await db.commit()
        await _flush_events(user_uuid, workspace_id, import_uuid, events)
        await job_events.emit(import_uuid, "job.failed", namespace=NAMESPACE, message=failure_message)
        if is_cancelled:
            raise
        return

    await _flush_events(user_uuid, workspace_id, import_uuid, events)
    await clear_cancel(CANCEL_KIND, import_uuid)
    if cancelled:
        await job_events.emit(
            import_uuid, "job.cancelled", namespace=NAMESPACE, message="Classificazione AI interrotta dall'utente"
        )
        return
    await job_events.emit(import_uuid, "job.completed", namespace=NAMESPACE, processed=total, total=total)


async def _classify_all(
    import_uuid: uuid.UUID,
    user_uuid: uuid.UUID,
    workspace_id: uuid.UUID,
    total: int,
    financial_account_id: uuid.UUID,
    events: list[PendingEvent],
) -> bool:
    """Ritorna True se l'utente ha interrotto la classificazione (le righe gia'
    classificate restano tali)."""
    async with rls_session(user_uuid) as db:
        active_ai_profile = await get_active_profile(db, workspace_id)
        if active_ai_profile is None:
            events.append(PendingEvent("warning", "skipped_no_profile", "profile_deactivated"))
            # Il profilo e' stato disattivato tra la fine dell'import e
            # l'esecuzione di questo job: nessun provider disponibile, non e'
            # un errore, semplicemente non c'e' piu' nulla da classificare.
            import_row = await db.get(Import, import_uuid)
            if import_row is not None:
                import_row.ai_classification_status = "skipped"
                await db.commit()
            return False
        ai_classifier = build_classifier(active_ai_profile)
        # Fetta 2 (PLAN_TAXONOMY_I18N.md): lingua di classificazione del
        # conto a cui appartiene questo import — None (mai impostata) vale
        # italiano, comportamento invariato per i conti esistenti.
        financial_account = await db.get(FinancialAccount, financial_account_id)
        classification_language = financial_account.classification_language if financial_account else None
        # Rework prompt AI: caricate UNA sola volta con kinds=None (tutte),
        # il filtro per kind/segno e' per-riga (righe diverse nello stesso
        # import possono avere direction/transaction_type diversi) — vedi
        # kinds_for_transaction() piu' sotto, applicato in Python prima di
        # ogni chiamata invece di interrogare il DB per ogni riga.
        ai_categories = await load_category_options(
            db, workspace_id, kinds=None, leaves_only=True, language=classification_language
        )
        ai_provider = active_ai_profile.provider
        ai_model = active_ai_profile.model
        # Letta una volta per l'intero job, non per riga: system_settings
        # non e' una cache di processo, ma rileggerla ad ogni transazione
        # sarebbe una query in piu' senza motivo (la soglia non cambia a
        # meta' di un job gia' in corso).
        needs_review_threshold = float(await get_setting_value(_NEEDS_REVIEW_THRESHOLD_KEY, 0.6))

        result = await db.execute(
            select(Transaction)
            .where(
                Transaction.workspace_id == workspace_id,
                Transaction.import_id == import_uuid,
                Transaction.category_id.is_(None),
                # Guardia negativa (doppia protezione, non solo assegnazione
                # nel livello deterministico di import_job.py): un
                # investimento/trasferimento/dividendo/interesse/tassa/
                # commissione non deve MAI arrivare all'AI, anche se la
                # categoria di sistema attesa per quel transaction_type e'
                # stata disattivata dall'utente (nel qual caso il livello
                # deterministico lascia la riga category_id IS NULL, che
                # altrimenti la farebbe ricadere qui). Risolve il bug reale
                # riportato dall'utente: un PAC su ETF (transaction_type
                # "investment") classificato dall'AI come "Tempo libero" o
                # "Abbonamenti" perche' nessun'altra categoria era disponibile.
                Transaction.transaction_type.notin_(AI_EXCLUDED_TRANSACTION_TYPES),
            )
            .order_by(Transaction.transaction_date)
        )
        unclassified = [
            _UnclassifiedRow(
                id=t.id,
                description_raw=t.description_raw,
                description_normalized=t.description_normalized,
                merchant=t.merchant,
                amount=str(t.amount),
                currency=t.currency,
                direction=t.direction,
                transaction_type=t.transaction_type,
                transaction_date=t.transaction_date.isoformat(),
                counterparty_name=t.counterparty_name,
            )
            for t in result.scalars().all()
        ]

    # Bug reale riportato dall'utente: un provider Ollama spento a meta'
    # import (container ucciso per simulare un crash) non fermava il job —
    # ogni chiamata falliva silenziosamente (AIProviderError -> None) ma il
    # contatore "processato" avanzava comunque per ogni riga, come se il
    # provider stesse rispondendo normalmente. Due correzioni:
    # 1) `ai_transactions_classified` riflette ora le classificazioni
    #    RIUSCITE, non i tentativi — durante un'interruzione del provider
    #    l'indicatore "x/N" smette onestamente di avanzare invece di fingere
    #    progresso.
    # 2) Un numero di fallimenti di PROVIDER (non "nessun match", quello e'
    #    un esito legittimo) consecutivi oltre soglia interrompe il job con
    #    stato 'failed' invece di continuare a scorrere l'intera coda
    #    sapendo gia' che ogni chiamata fallira' comunque.
    #
    # Concorrenza (rework prompt AI): N chiamate in volo contemporaneamente
    # invece di una alla volta — Ollama locale serializza comunque sulla GPU
    # (alzarla non guadagna nulla, resta fissa a 1), i provider cloud
    # guadagnano un throughput ~N x. A parita' di batch, `asyncio.gather`
    # preserva l'ordine dei risultati rispetto all'ordine di invio (non
    # l'ordine di completamento), quindi la logica sotto resta deterministica
    # riga per riga esattamente come nella versione sequenziale.
    max_concurrency = 1 if ai_classifier.provider == "ollama" else get_settings().ai_max_concurrency

    processed = 0
    classified = 0
    no_match = 0
    provider_errors = 0
    consecutive_provider_errors = 0
    cancelled = False
    for batch_start in range(0, len(unclassified), max_concurrency):
        # Interruzione chiesta dall'utente: ci si ferma tra un gruppo e l'altro,
        # mai a meta' di una scrittura.
        if await is_cancel_requested(CANCEL_KIND, import_uuid):
            cancelled = True
            break
        batch = unclassified[batch_start : batch_start + max_concurrency]
        attempts = await asyncio.gather(
            *[
                classify_transaction(
                    ai_classifier,
                    _categories_for_row(ai_categories, row),
                    ClassifiableTransaction(
                        description_raw=row.description_raw,
                        description_normalized=row.description_normalized,
                        merchant=row.merchant,
                        amount=row.amount,
                        currency=row.currency,
                        direction=row.direction,
                        transaction_type=row.transaction_type,
                        transaction_date=row.transaction_date,
                        counterparty_name=row.counterparty_name,
                    ),
                    classification_language,
                )
                for row in batch
            ]
        )

        for row, attempt in zip(batch, attempts):
            if attempt.provider_error:
                provider_errors += 1
                if provider_errors <= MAX_ERROR_EVENTS_PER_RUN:
                    events.append(PendingEvent("error", "provider_error", attempt.error_detail or "unknown"))
                consecutive_provider_errors += 1
                if consecutive_provider_errors >= _MAX_CONSECUTIVE_PROVIDER_ERRORS:
                    raise AIProviderUnavailableError(
                        f"provider AI non raggiungibile per {consecutive_provider_errors} "
                        "tentativi consecutivi, job interrotto"
                    )
            else:
                consecutive_provider_errors = 0

            # Dettaglio leggibile per riga (cruscotto "Attivita'"): serve solo
            # a raccontare cosa sta succedendo in questo momento, mai usato
            # per decisioni applicative (quelle restano su category_id/
            # Classification, non sul testo di un evento SSE).
            detail: str | None = None
            if attempt.result is not None:
                async with rls_session(user_uuid) as db:
                    txn = await db.get(Transaction, row.id)
                    # Una correzione manuale dell'utente ha sempre priorita'
                    # sull'AI (regola non negoziabile): se nel frattempo
                    # qualcuno ha gia' assegnato una categoria a questa
                    # transazione, non la si sovrascrive.
                    if txn is not None and txn.category_id is None:
                        txn.category_id = attempt.result.category_id
                        score = compute_ai_confidence(
                            attempt.result.raw_confidence, has_merchant=row.merchant is not None
                        )
                        txn.needs_review = score_needs_review(score, needs_review_threshold)
                        db.add(
                            Classification(
                                transaction_id=txn.id,
                                method="ai",
                                provider=ai_provider,
                                model=ai_model,
                                category_id=attempt.result.category_id,
                                score=score,
                                explanation=attempt.result.explanation,
                            )
                        )
                        matched = next((c for c in ai_categories if c.id == attempt.result.category_id), None)
                        detail = f"Assegnata a {matched.name if matched else 'categoria'} (AI)"
                    await db.commit()
                classified += 1
            elif attempt.provider_error:
                detail = "Provider AI non raggiungibile per questa transazione"
            else:
                no_match += 1
                detail = "Nessuna categoria pertinente trovata"

            processed += 1
            async with rls_session(user_uuid) as db:
                import_row = await db.get(Import, import_uuid)
                if import_row is not None:
                    # `classified`, non `processed`: il nome del campo
                    # ("ai_transactions_classified") promette un conteggio di
                    # successi, non di tentativi — vedi il commento sopra sul
                    # bug del provider spento a meta' import.
                    import_row.ai_transactions_classified = classified
                    await db.commit()
            await job_events.emit(
                import_uuid,
                "job.progress",
                namespace=NAMESPACE,
                processed=classified,
                total=total,
                detail=detail,
            )

    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is not None:
            import_row.ai_classification_status = "cancelled" if cancelled else "completed"
            await db.commit()
    events.append(
        PendingEvent(
            "warning" if (provider_errors or cancelled) else "info",
            "cancelled_by_user" if cancelled else "run_completed",
            f"classified={classified} no_match={no_match} provider_errors={provider_errors} total={total}",
        )
    )
    return cancelled

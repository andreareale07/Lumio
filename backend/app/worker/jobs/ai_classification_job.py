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

from app.ai.base import ClassifiableTransaction
from app.ai.registry import build_classifier
from app.db.rls import rls_session
from app.models.classification import Classification
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.services import job_events
from app.services.ai_classification import classify_transaction, load_category_options
from app.services.ai_profile_service import get_active_profile
from app.services.confidence import compute_ai_confidence

logger = logging.getLogger("lumio.worker.ai_classification_job")

NAMESPACE = "ai_classification"


@dataclass
class _UnclassifiedRow:
    id: uuid.UUID
    description_raw: str
    description_normalized: str
    merchant: str | None
    amount: str
    currency: str
    direction: str


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
        total = import_row.ai_transactions_total
        import_row.ai_classification_status = "running"
        await db.commit()

    await job_events.emit(import_uuid, "job.started", namespace=NAMESPACE, processed=0, total=total)

    try:
        await _classify_all(import_uuid, user_uuid, workspace_id, total)
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
        async with rls_session(user_uuid) as db:
            import_row = await db.get(Import, import_uuid)
            if import_row is not None:
                import_row.ai_classification_status = "failed"
                await db.commit()
        await job_events.emit(
            import_uuid, "job.failed", namespace=NAMESPACE, message="Classificazione AI interrotta"
        )
        if is_cancelled:
            raise
        return

    await job_events.emit(import_uuid, "job.completed", namespace=NAMESPACE, processed=total, total=total)


async def _classify_all(import_uuid: uuid.UUID, user_uuid: uuid.UUID, workspace_id: uuid.UUID, total: int) -> None:
    async with rls_session(user_uuid) as db:
        active_ai_profile = await get_active_profile(db, workspace_id)
        if active_ai_profile is None:
            # Il profilo e' stato disattivato tra la fine dell'import e
            # l'esecuzione di questo job: nessun provider disponibile, non e'
            # un errore, semplicemente non c'e' piu' nulla da classificare.
            import_row = await db.get(Import, import_uuid)
            if import_row is not None:
                import_row.ai_classification_status = "skipped"
                await db.commit()
            return
        ai_classifier = build_classifier(active_ai_profile)
        ai_categories = await load_category_options(db, workspace_id)
        ai_provider = active_ai_profile.provider
        ai_model = active_ai_profile.model

        result = await db.execute(
            select(Transaction)
            .where(
                Transaction.workspace_id == workspace_id,
                Transaction.import_id == import_uuid,
                Transaction.category_id.is_(None),
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
            )
            for t in result.scalars().all()
        ]

    processed = 0
    for row in unclassified:
        ai_result = await classify_transaction(
            ai_classifier,
            ai_categories,
            ClassifiableTransaction(
                description_raw=row.description_raw,
                description_normalized=row.description_normalized,
                merchant=row.merchant,
                amount=row.amount,
                currency=row.currency,
                direction=row.direction,
            ),
        )
        if ai_result is not None:
            async with rls_session(user_uuid) as db:
                txn = await db.get(Transaction, row.id)
                # Una correzione manuale dell'utente ha sempre priorita'
                # sull'AI (regola non negoziabile): se nel frattempo qualcuno
                # ha gia' assegnato una categoria a questa transazione, non
                # la si sovrascrive.
                if txn is not None and txn.category_id is None:
                    txn.category_id = ai_result.category_id
                    db.add(
                        Classification(
                            transaction_id=txn.id,
                            method="ai",
                            provider=ai_provider,
                            model=ai_model,
                            category_id=ai_result.category_id,
                            score=compute_ai_confidence(
                                ai_result.raw_confidence, has_merchant=row.merchant is not None
                            ),
                            explanation=ai_result.explanation,
                        )
                    )
                await db.commit()

        processed += 1
        async with rls_session(user_uuid) as db:
            import_row = await db.get(Import, import_uuid)
            if import_row is not None:
                import_row.ai_transactions_classified = processed
                await db.commit()
        await job_events.emit(import_uuid, "job.progress", namespace=NAMESPACE, processed=processed, total=total)

    async with rls_session(user_uuid) as db:
        import_row = await db.get(Import, import_uuid)
        if import_row is not None:
            import_row.ai_classification_status = "completed"
            await db.commit()

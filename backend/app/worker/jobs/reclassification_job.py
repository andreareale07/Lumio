"""Job di riclassificazione (rework tassonomia/pipeline di classificazione):
permette di riapplicare la pipeline (regole utente -> sistema -> opzionalmente
AI) alle transazioni GIA' importate, senza dover reimportare — necessario
perche' la tassonomia e' cambiata (migration 0021/0022, nuove categorie,
nuovo catalogo di pattern di sistema) dopo che l'utente aveva gia'
classificato mesi di storico con quella vecchia. E' lo stesso meccanismo che
risolve concretamente, sui dati gia' importati, il bug reale riportato
dall'utente (un PAC su ETF classificato dall'AI come "Tempo libero").

Regola non negoziabile, resa ESATTA — non un'euristica come altrove nel
progetto (es. `transfer_recognition.reapply_internal_transfer_detection`,
che confronta col default del parser): una transazione con una
`Classification(method IN ('user', 'manual'))` non viene MAI toccata,
verificato con `NOT EXISTS` sullo storico append-only di `classifications`,
non su un confronto di valori che potrebbe sbagliare.

Seconda invariante: la riclassificazione non azzera MAI una `category_id`
esistente se un livello della pipeline restituisce `None` per quella riga —
solo AGGIUNGE o CORREGGE un'assegnazione, non la rimuove mai.

Fasi (ognuna committata per riga, stesso principio di
`ai_classification_job.py`: il job e' interrompibile e riprendibile senza
stato parziale, una riesecuzione e' idempotente perche' le righe gia'
sistemate non sono piu' eleggibili o non cambiano risultato):
1. backfill merchant — su TUTTE le transazioni del workspace con
   `merchant IS NULL` (arricchimento puro, non tocca `category_id`: si
   applica anche alle righe corrette a mano, che restano intoccate nelle
   fasi successive).
2. regole utente + livello di sistema (deterministico) sulle righe
   eleggibili per `scope`.
3. AI (solo se `run_ai=True` e un profilo e' attivo) sulle righe rimaste
   senza categoria dopo la fase 2.
"""
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.ai.base import ClassifiableTransaction
from app.ai.registry import build_classifier
from app.db.rls import rls_session
from app.models.classification import Classification
from app.models.transaction import Transaction
from app.services import job_events
from app.services.ai_classification import classify_transaction, kinds_for_transaction, load_category_options
from app.services.ai_profile_service import get_active_profile
from app.services.classification_loader import load_eligible_transaction_ids, load_pipeline_context
from app.services.classification_pipeline import ClassifiableRow, classify_deterministic
from app.services.confidence import compute_ai_confidence
from app.services.confidence import needs_review as score_needs_review
from app.services.job_run_tracker import tracked_job_run
from app.services.merchant_extraction import extract_merchant
from app.services.system_classification import is_ai_eligible
from app.services.system_settings_service import get_setting_value

logger = logging.getLogger("lumio.worker.reclassification_job")

JOB_KIND = "reclassification"
NAMESPACE = "reclassification"
_NEEDS_REVIEW_THRESHOLD_KEY = "classification.needs_review_threshold"


@dataclass
class ReclassificationStats:
    total_candidates: int = 0
    merchant_backfilled: int = 0
    deterministic: int = 0
    ai_classified: int = 0
    ai_skipped_provider_error: int = 0


async def _backfill_merchant(workspace_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """Fase 1 — arricchimento puro, NESSUN filtro su classificazione
    manuale: il merchant e' un dato descrittivo, non una decisione, quindi
    si applica anche alle righe che l'utente ha gia' corretto a mano."""
    async with rls_session(user_id) as db:
        result = await db.execute(
            select(Transaction.id, Transaction.description_raw).where(
                Transaction.workspace_id == workspace_id, Transaction.merchant.is_(None)
            )
        )
        rows = result.all()

    backfilled = 0
    for txn_id, description_raw in rows:
        merchant = extract_merchant(description_raw)
        if merchant is None:
            continue
        async with rls_session(user_id) as db:
            txn = await db.get(Transaction, txn_id)
            if txn is not None and txn.merchant is None:
                txn.merchant = merchant
                await db.commit()
        backfilled += 1
    return backfilled


async def _eligible_transaction_ids(workspace_id: uuid.UUID, user_id: uuid.UUID, scope: str) -> list[uuid.UUID]:
    async with rls_session(user_id) as db:
        return await load_eligible_transaction_ids(db, workspace_id, scope)


async def _run_deterministic_phase(
    workspace_id: uuid.UUID, user_id: uuid.UUID, transaction_ids: list[uuid.UUID], total_for_progress: int
) -> int:
    async with rls_session(user_id) as db:
        pipeline_ctx = await load_pipeline_context(db, workspace_id)
        # Per il dettaglio del cruscotto "Attivita'": nomi leggibili invece
        # del solo category_id nell'evento SSE.
        category_names = {c.id: c.name for c in await load_category_options(db, workspace_id)}
    needs_review_threshold = float(await get_setting_value(_NEEDS_REVIEW_THRESHOLD_KEY, 0.6))

    classified = 0
    for index, txn_id in enumerate(transaction_ids, start=1):
        async with rls_session(user_id) as db:
            txn = await db.get(Transaction, txn_id)
            if txn is None:
                continue
            row = ClassifiableRow(
                description_raw=txn.description_raw,
                description_normalized=txn.description_normalized,
                merchant=txn.merchant,
                transaction_type=txn.transaction_type,
            )
            outcome = classify_deterministic(pipeline_ctx, row)
            # Scrive solo se e' un cambiamento REALE: senza questo controllo,
            # una riesecuzione del job (idempotenza) aggiungerebbe una nuova
            # riga di `Classification` identica ad ogni giro, anche quando
            # la pipeline propone esattamente la stessa categoria gia'
            # assegnata — storico rumoroso senza alcuna informazione nuova.
            detail = "Nessuna categoria deterministica trovata"
            if outcome is not None and outcome.category_id != txn.category_id:
                txn.category_id = outcome.category_id
                txn.needs_review = score_needs_review(outcome.score, needs_review_threshold)
                db.add(
                    Classification(
                        transaction_id=txn.id,
                        method=outcome.method,
                        category_id=outcome.category_id,
                        score=outcome.score,
                        explanation=outcome.explanation,
                    )
                )
                await db.commit()
                classified += 1
                category_label = category_names.get(outcome.category_id, "categoria")
                method_label = "regola" if outcome.method == "rule" else "sistema"
                detail = f"Assegnata a {category_label} ({method_label})"
        await job_events.emit(
            workspace_id,
            "job.progress",
            namespace=NAMESPACE,
            processed=index,
            total=total_for_progress,
            detail=detail,
        )
    return classified


async def _run_ai_phase(
    workspace_id: uuid.UUID, user_id: uuid.UUID, transaction_ids: list[uuid.UUID]
) -> tuple[int, int]:
    async with rls_session(user_id) as db:
        active_ai_profile = await get_active_profile(db, workspace_id)
        if active_ai_profile is None:
            return 0, 0
        ai_classifier = build_classifier(active_ai_profile)
        ai_categories = await load_category_options(db, workspace_id, kinds=None, leaves_only=True)
        ai_provider = active_ai_profile.provider
        ai_model = active_ai_profile.model
    needs_review_threshold = float(await get_setting_value(_NEEDS_REVIEW_THRESHOLD_KEY, 0.6))

    category_names = {c.id: c.name for c in ai_categories}
    ai_eligible_ids = []
    for txn_id in transaction_ids:
        async with rls_session(user_id) as db:
            txn = await db.get(Transaction, txn_id)
            if txn is not None and txn.category_id is None and is_ai_eligible(txn.transaction_type):
                ai_eligible_ids.append(txn_id)
    total_ai = len(ai_eligible_ids)

    classified = 0
    provider_errors = 0
    for index, txn_id in enumerate(ai_eligible_ids, start=1):
        detail = "Nessuna categoria trovata"
        async with rls_session(user_id) as db:
            txn = await db.get(Transaction, txn_id)
            if txn is None or txn.category_id is not None:
                continue
            row_kinds = kinds_for_transaction(txn.direction, txn.transaction_type)
            row_categories = [c for c in ai_categories if c.kind in row_kinds]

            attempt = await classify_transaction(
                ai_classifier,
                row_categories,
                ClassifiableTransaction(
                    description_raw=txn.description_raw,
                    description_normalized=txn.description_normalized,
                    merchant=txn.merchant,
                    amount=str(txn.amount),
                    currency=txn.currency,
                    direction=txn.direction,
                    transaction_type=txn.transaction_type,
                    transaction_date=txn.transaction_date.isoformat(),
                    counterparty_name=txn.counterparty_name,
                ),
            )
            if attempt.provider_error:
                provider_errors += 1
                detail = "Provider AI non raggiungibile per questa transazione"
            elif attempt.result is not None and txn.category_id is None:
                txn.category_id = attempt.result.category_id
                score = compute_ai_confidence(attempt.result.raw_confidence, has_merchant=txn.merchant is not None)
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
                await db.commit()
                classified += 1
                detail = f"Assegnata a {category_names.get(attempt.result.category_id, 'categoria')} (AI)"
        await job_events.emit(
            workspace_id, "job.progress", namespace=NAMESPACE, processed=index, total=total_ai, detail=detail
        )
    return classified, provider_errors


async def _reclassify(workspace_id: uuid.UUID, user_id: uuid.UUID, scope: str, run_ai: bool) -> ReclassificationStats:
    stats = ReclassificationStats()

    stats.merchant_backfilled = await _backfill_merchant(workspace_id, user_id)

    transaction_ids = await _eligible_transaction_ids(workspace_id, user_id, scope)
    stats.total_candidates = len(transaction_ids)
    await job_events.emit(
        workspace_id, "job.progress", namespace=NAMESPACE, processed=0, total=stats.total_candidates
    )

    stats.deterministic = await _run_deterministic_phase(
        workspace_id, user_id, transaction_ids, stats.total_candidates
    )

    if run_ai:
        stats.ai_classified, stats.ai_skipped_provider_error = await _run_ai_phase(
            workspace_id, user_id, transaction_ids
        )

    return stats


async def reclassify_workspace_job(ctx, workspace_id: str, user_id: str, scope: str, run_ai: bool) -> None:
    ws_id = uuid.UUID(workspace_id)
    uid = uuid.UUID(user_id)

    async with tracked_job_run(ws_id, uid, JOB_KIND) as run:
        stats = await _reclassify(ws_id, uid, scope, run_ai)
        run.message = (
            f"{stats.merchant_backfilled} merchant aggiornati, "
            f"{stats.deterministic} classificate deterministicamente"
            + (f", {stats.ai_classified} classificate dall'AI" if run_ai else "")
            + "."
        )
        await job_events.emit(
            ws_id, "job.completed", namespace=NAMESPACE, processed=stats.total_candidates, total=stats.total_candidates
        )

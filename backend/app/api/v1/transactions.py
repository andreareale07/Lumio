import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.category import Category
from app.models.classification import Classification
from app.models.financial_account import FinancialAccount
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transactions import (
    ClassificationOut,
    TransactionCreate,
    TransactionOut,
    TransactionReviewSummaryOut,
    TransactionUpdate,
)
from app.services.audit_log_service import log_event
from app.services.confidence import needs_review as score_needs_review
from app.services.csv_import import collapse_whitespace
from app.services.rule_loader import load_active_rule_specs
from app.services.rules_engine import Probe, evaluate
from app.services.system_settings_service import get_setting_value
from app.services.transaction_dedup import compute_dedup_fingerprint

router = APIRouter(prefix="/transactions", tags=["transactions"])

_NEEDS_REVIEW_THRESHOLD_KEY = "classification.needs_review_threshold"


def _is_pending_review(transaction: type[Transaction] = Transaction):
    """SPEC §43 ("319 classificati, 8 da verificare"): "da verificare" copre
    sia le transazioni classificate ma incerte (`needs_review=True`) sia
    quelle mai classificate (`category_id IS NULL`, es. rimaste indietro
    perche' il job AI e' stato interrotto) — entrambe meritano un secondo
    sguardo dell'utente, anche se per motivi diversi. Unica definizione,
    condivisa tra il filtro della lista e il conteggio di riepilogo: usarne
    due diverse (bug reale) fa si' che il badge mostri un numero che la
    lista filtrata non trova mai."""
    return or_(transaction.needs_review.is_(True), transaction.category_id.is_(None))


async def _get_transaction_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, transaction_id: uuid.UUID
) -> Transaction:
    transaction = await db.get(Transaction, transaction_id)
    if transaction is None or transaction.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return transaction


async def _assert_account_in_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    account = await db.get(FinancialAccount, account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid financial_account_id")


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    await _assert_account_in_workspace(db, workspace_id, payload.financial_account_id)
    data = payload.model_dump()

    # Transaction Deduplication Engine (docs/SPEC_DEDUP_TRANSACTION.md):
    # description_normalized non e' un campo di TransactionCreate (l'utente
    # non lo compila a mano) ma deve SEMPRE essere valorizzata — e' un
    # input del fingerprint, e il fallback a description_raw dentro
    # compute_dedup_fingerprint e' pensato solo per dati legacy/backfill,
    # mai per una riga creata da qui in avanti.
    data["description_normalized"] = collapse_whitespace(data["description_raw"])
    data["dedup_fingerprint"] = compute_dedup_fingerprint(
        workspace_id=workspace_id,
        financial_account_id=data["financial_account_id"],
        transaction_date=data["transaction_date"],
        amount=data["amount"],
        currency=data["currency"],
        description_normalized=data["description_normalized"],
        description_raw=data["description_raw"],
        transaction_type=data["transaction_type"],
    )

    # Se il chiamante non fornisce esplicitamente una categoria, prova il
    # motore regole (SPEC §23: prima di qualsiasi AI, che in M06 non esiste
    # ancora). Se il chiamante la fornisce, e' una classificazione 'manual'
    # (SPEC §24) — nessuna riga di storico se resta non classificata.
    classification_method: str | None = "manual" if data["category_id"] is not None else None
    if classification_method is None:
        active_rules = await load_active_rule_specs(db, workspace_id)
        probe = Probe(
            description_raw=data["description_raw"],
            description_normalized=None,
            merchant=data["merchant"],
        )
        matched_category_id = evaluate(active_rules, probe)
        if matched_category_id is not None:
            data["category_id"] = matched_category_id
            classification_method = "rule"

    transaction = Transaction(workspace_id=workspace_id, **data)
    db.add(transaction)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id") from exc

    if classification_method is not None:
        score = Decimal("1.00") if classification_method == "rule" else None
        # 'manual' (l'utente ha scelto la categoria alla creazione): mai da
        # verificare, non ha senso segnalare come incerta una scelta
        # dell'utente stesso. 'rule': punteggio fisso 1.00, sotto qualunque
        # soglia sensata, ma il confronto resta esplicito per coerenza con
        # gli altri scrittori.
        transaction.needs_review = (
            False
            if classification_method == "manual"
            else score_needs_review(score, float(await get_setting_value(_NEEDS_REVIEW_THRESHOLD_KEY, 0.6)))
        )
        db.add(
            Classification(
                transaction_id=transaction.id,
                method=classification_method,
                category_id=transaction.category_id,
                score=score,
            )
        )

    await db.commit()
    return transaction


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    financial_account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    transaction_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    needs_review: bool | None = None,
    import_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Transaction]:
    query = select(Transaction).where(Transaction.workspace_id == workspace_id)
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)
    if needs_review is True:
        query = query.where(_is_pending_review())
    elif needs_review is False:
        query = query.where(~_is_pending_review())
    if import_id is not None:
        query = query.where(Transaction.import_id == import_id)
    if category_id is not None:
        # Match padre-O-figlio, non solo esatto: `category_id` qui e' spesso
        # un group_id riaccorpato (come in analytics.by_merchant, stesso
        # pattern) — puo' essere una categoria padre, e le transazioni sono
        # taggate con la SOTTOCATEGORIA figlia, non col padre stesso. Senza
        # questo, un link "vedi le transazioni di Trasporti" da una futura
        # pagina di dettaglio KPI restituirebbe sempre una lista vuota (bug
        # gia' risolto in by_merchant, qui replicato).
        query = query.outerjoin(Category, Transaction.category_id == Category.id).where(
            or_(Transaction.category_id == category_id, Category.parent_id == category_id)
        )
    if transaction_type is not None:
        query = query.where(Transaction.transaction_type == transaction_type)
    if date_from is not None:
        query = query.where(Transaction.transaction_date >= date_from)
    if date_to is not None:
        query = query.where(Transaction.transaction_date <= date_to)

    query = query.order_by(Transaction.transaction_date.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/review-summary", response_model=TransactionReviewSummaryOut)
async def get_transaction_review_summary(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    financial_account_id: uuid.UUID | None = None,
    import_id: uuid.UUID | None = None,
) -> TransactionReviewSummaryOut:
    """SPEC §43 ("319 classificati, 8 da verificare"): 'risolta' = ha una
    categoria assegnata E non e' `needs_review` — 'da verificare' e' il
    complemento (include sia le incerte sia le mai classificate, entrambe
    meritano un secondo sguardo dell'utente, per motivi diversi). Nessuna
    riga trasferita al client solo per contare: aggregazione lato DB."""
    base_query = select(Transaction).where(Transaction.workspace_id == workspace_id)
    if financial_account_id is not None:
        base_query = base_query.where(Transaction.financial_account_id == financial_account_id)
    if import_id is not None:
        base_query = base_query.where(Transaction.import_id == import_id)

    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar_one()

    pending_query = base_query.where(_is_pending_review())
    pending_result = await db.execute(select(func.count()).select_from(pending_query.subquery()))
    pending = pending_result.scalar_one()

    return TransactionReviewSummaryOut(total=total, classified=total - pending, needs_review=pending)


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_transaction(
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    return await _get_transaction_or_404(db, workspace_id, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionOut)
async def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Transaction:
    transaction = await _get_transaction_or_404(db, workspace_id, transaction_id)
    updates = payload.model_dump(exclude_unset=True)
    # Una modifica esplicita di category_id e' una correzione (SPEC §24,
    # method='user'): e' lo storico da cui parte la proposta di regola
    # automatica dopo correzioni ripetute (SPEC §29, vedi /rules/suggestions).
    category_corrected = "category_id" in updates and updates["category_id"] != transaction.category_id
    # Campi di identita' del fingerprint esposti da TransactionUpdate
    # (amount/currency/financial_account_id non sono modificabili da questo
    # endpoint): se uno di questi cambia, il dedup_fingerprint persistito
    # resterebbe stale rispetto al contenuto reale della transazione,
    # producendo falsi (non-)match nei futuri import — vedi
    # docs/SPEC_DEDUP_TRANSACTION.md e il piano approvato.
    fingerprint_fields = {"transaction_date", "description_normalized", "transaction_type"}
    identity_changed = bool(fingerprint_fields & updates.keys())
    for field, value in updates.items():
        setattr(transaction, field, value)

    if identity_changed:
        transaction.dedup_fingerprint = compute_dedup_fingerprint(
            workspace_id=transaction.workspace_id,
            financial_account_id=transaction.financial_account_id,
            transaction_date=transaction.transaction_date,
            amount=transaction.amount,
            currency=transaction.currency,
            description_normalized=transaction.description_normalized,
            description_raw=transaction.description_raw,
            transaction_type=transaction.transaction_type,
        )

    if category_corrected:
        # Una correzione manuale chiude SEMPRE la review, incondizionatamente
        # (non un confronto con la soglia: l'utente ha gia' deciso, non c'e'
        # altro da verificare) — indipendentemente da cosa l'aveva sollevata
        # in precedenza (AI incerta, o una riga poi reclassificata).
        transaction.needs_review = False
        db.add(
            Classification(
                transaction_id=transaction.id,
                method="user",
                category_id=transaction.category_id,
                created_by_user_id=user.id,
            )
        )

    if updates:
        await log_event(
            db, workspace_id, user.id, "TRANSACTION_UPDATED", entity_type="transaction", entity_id=transaction.id
        )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid category_id") from exc
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    transaction = await _get_transaction_or_404(db, workspace_id, transaction_id)
    await db.delete(transaction)
    await db.commit()


@router.get("/{transaction_id}/classifications", response_model=list[ClassificationOut])
async def list_transaction_classifications(
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[Classification]:
    await _get_transaction_or_404(db, workspace_id, transaction_id)
    result = await db.execute(
        select(Classification)
        .where(Classification.transaction_id == transaction_id)
        .order_by(Classification.created_at.desc())
    )
    return list(result.scalars().all())

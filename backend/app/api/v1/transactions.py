import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.classification import Classification
from app.models.financial_account import FinancialAccount
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transactions import (
    ClassificationOut,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services.audit_log_service import log_event
from app.services.rule_loader import load_active_rule_specs
from app.services.rules_engine import Probe, evaluate

router = APIRouter(prefix="/transactions", tags=["transactions"])


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
        db.add(
            Classification(
                transaction_id=transaction.id,
                method=classification_method,
                category_id=transaction.category_id,
                score=Decimal("1.00") if classification_method == "rule" else None,
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
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Transaction]:
    query = select(Transaction).where(Transaction.workspace_id == workspace_id)
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)
    if category_id is not None:
        query = query.where(Transaction.category_id == category_id)
    if transaction_type is not None:
        query = query.where(Transaction.transaction_type == transaction_type)
    if date_from is not None:
        query = query.where(Transaction.transaction_date >= date_from)
    if date_to is not None:
        query = query.where(Transaction.transaction_date <= date_to)

    query = query.order_by(Transaction.transaction_date.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


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
    for field, value in updates.items():
        setattr(transaction, field, value)

    if category_corrected:
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

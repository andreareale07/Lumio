import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.models.asset import Asset
from app.models.financial_account import FinancialAccount
from app.models.investment_transaction import InvestmentTransaction
from app.models.transaction import Transaction
from app.schemas.investment_transactions import (
    InvestmentBackfillResult,
    InvestmentTransactionCreate,
    InvestmentTransactionOut,
    InvestmentTransactionUpdate,
)
from app.services.investment_backfill import backfill_investment_transactions
from app.services.position_service import recompute_position

router = APIRouter(prefix="/investment-transactions", tags=["portfolio"])


async def _get_investment_transaction_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, investment_transaction_id: uuid.UUID
) -> InvestmentTransaction:
    txn = await db.get(InvestmentTransaction, investment_transaction_id)
    if txn is None or txn.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investment transaction not found")
    return txn


async def _assert_account_in_workspace(db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID) -> None:
    account = await db.get(FinancialAccount, account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid financial_account_id")


async def _assert_asset_in_workspace(db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID | None) -> None:
    if asset_id is None:
        return
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid asset_id")


async def _assert_bank_transaction_in_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, transaction_id: uuid.UUID | None
) -> None:
    if transaction_id is None:
        return
    transaction = await db.get(Transaction, transaction_id)
    if transaction is None or transaction.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid transaction_id")


async def _recompute_or_400(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    asset_id: uuid.UUID | None,
    currency: str,
) -> None:
    """Ricalcola la posizione e blocca (400) se il nuovo stato e' inconsistente
    (es. una vendita che eccede la quantita' posseduta) — solo per
    create/update, mai per delete (vedi commento nel router: cancellare un
    movimento e' sempre permesso, l'eventuale incoerenza risultante resta
    visibile nella posizione, non nascosta)."""
    if asset_id is None:
        return  # deposit/withdrawal/fee senza asset: nessuna posizione da calcolare
    _, warnings = await recompute_position(db, workspace_id, financial_account_id, asset_id, currency)
    if warnings:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "; ".join(warnings))


@router.post("", response_model=InvestmentTransactionOut, status_code=status.HTTP_201_CREATED)
async def create_investment_transaction(
    payload: InvestmentTransactionCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> InvestmentTransaction:
    await _assert_account_in_workspace(db, workspace_id, payload.financial_account_id)
    await _assert_asset_in_workspace(db, workspace_id, payload.asset_id)
    await _assert_bank_transaction_in_workspace(db, workspace_id, payload.transaction_id)

    txn = InvestmentTransaction(workspace_id=workspace_id, **payload.model_dump())
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reference") from exc

    await _recompute_or_400(db, workspace_id, txn.financial_account_id, txn.asset_id, txn.currency)
    await db.commit()
    return txn


@router.get("", response_model=list[InvestmentTransactionOut])
async def list_investment_transactions(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    financial_account_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[InvestmentTransaction]:
    query = select(InvestmentTransaction).where(InvestmentTransaction.workspace_id == workspace_id)
    if financial_account_id is not None:
        query = query.where(InvestmentTransaction.financial_account_id == financial_account_id)
    if asset_id is not None:
        query = query.where(InvestmentTransaction.asset_id == asset_id)
    if type is not None:
        query = query.where(InvestmentTransaction.type == type)
    if date_from is not None:
        query = query.where(InvestmentTransaction.trade_date >= date_from)
    if date_to is not None:
        query = query.where(InvestmentTransaction.trade_date <= date_to)

    query = query.order_by(InvestmentTransaction.trade_date.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{investment_transaction_id}", response_model=InvestmentTransactionOut)
async def get_investment_transaction(
    investment_transaction_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> InvestmentTransaction:
    return await _get_investment_transaction_or_404(db, workspace_id, investment_transaction_id)


@router.patch("/{investment_transaction_id}", response_model=InvestmentTransactionOut)
async def update_investment_transaction(
    investment_transaction_id: uuid.UUID,
    payload: InvestmentTransactionUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> InvestmentTransaction:
    txn = await _get_investment_transaction_or_404(db, workspace_id, investment_transaction_id)
    # (account, asset) PRECEDENTI: se la modifica sposta il movimento su
    # un'altra coppia, anche la vecchia posizione va ricalcolata (altrimenti
    # resterebbe stantia, con un movimento che non esiste piu' li').
    old_account_id, old_asset_id, old_currency = txn.financial_account_id, txn.asset_id, txn.currency

    updates = payload.model_dump(exclude_unset=True)
    if "asset_id" in updates:
        await _assert_asset_in_workspace(db, workspace_id, updates["asset_id"])
    if "transaction_id" in updates:
        await _assert_bank_transaction_in_workspace(db, workspace_id, updates["transaction_id"])
    for field, value in updates.items():
        setattr(txn, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reference") from exc

    if old_asset_id is not None and old_asset_id != txn.asset_id:
        await recompute_position(db, workspace_id, old_account_id, old_asset_id, old_currency)
    await _recompute_or_400(db, workspace_id, txn.financial_account_id, txn.asset_id, txn.currency)
    await db.commit()
    return txn


@router.delete("/{investment_transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investment_transaction(
    investment_transaction_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    txn = await _get_investment_transaction_or_404(db, workspace_id, investment_transaction_id)
    account_id, asset_id, currency = txn.financial_account_id, txn.asset_id, txn.currency
    await db.delete(txn)
    await db.flush()
    # Cancellare e' sempre permesso: un'eventuale incoerenza risultante (es.
    # una sell rimasta senza il buy che la precedeva) resta visibile nella
    # posizione ricalcolata, non bloccata qui (vedi docstring di
    # _recompute_or_400).
    if asset_id is not None:
        await recompute_position(db, workspace_id, account_id, asset_id, currency)
    await db.commit()


@router.post("/backfill", response_model=InvestmentBackfillResult)
async def backfill_investment_transactions_endpoint(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> InvestmentBackfillResult:
    """Milestone 09c: deriva i movimenti mancanti dalle transazioni
    'investment' gia' importate PRIMA che questo parsing automatico
    esistesse (o comunque non ancora collegate). Operazione sincrona (non
    un job async): pura scrittura DB su al massimo qualche centinaio di
    righe personali, nessuna chiamata di rete — non e' "un'operazione
    lunga" nel senso di CLAUDE.md. Idempotente: rieseguibile senza
    duplicare nulla."""
    result = await backfill_investment_transactions(db, workspace_id)
    await db.commit()
    return InvestmentBackfillResult(
        scanned=result.scanned,
        created=result.created,
        skipped_already_linked=result.skipped_already_linked,
        skipped_unrecognized=result.skipped_unrecognized,
    )

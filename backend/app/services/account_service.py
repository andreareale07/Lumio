"""Creazione conto — estratta da `app/api/v1/accounts.py` per essere
riusabile anche da `POST /imports/{id}/resolve-account` (creazione "al volo"
di un conto durante l'import, con IBAN precompilato dal documento). Non fa
commit: il chiamante decide il confine di transazione (un solo commit a fine
richiesta, stesso principio gia' seguito ovunque nel modulo — vedi
`app/db/rls.py`)."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_account import FinancialAccount
from app.schemas.accounts import FinancialAccountCreate
from app.services.currency_service import currency_exists
from app.services.transfer_recognition import reapply_internal_transfer_detection


async def create_financial_account(
    db: AsyncSession, workspace_id: uuid.UUID, payload: FinancialAccountCreate
) -> FinancialAccount:
    if not await currency_exists(db, workspace_id, payload.currency):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown currency code")
    account = FinancialAccount(workspace_id=workspace_id, **payload.model_dump())
    db.add(account)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid bank reference") from exc

    # Milestone 09.5b: un conto creato con l'IBAN gia' compilato puo' far
    # riconoscere trasferimenti interni gia' importati su ALTRI conti (SPEC
    # §37) — es. il conto corrente si registra dopo l'estratto TR che
    # riporta gia' un bonifico verso di esso.
    if account.iban:
        await reapply_internal_transfer_detection(db, workspace_id)
    return account

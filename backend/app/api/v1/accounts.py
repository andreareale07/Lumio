import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.models.financial_account import FinancialAccount
from app.models.financial_account_iban_history import FinancialAccountIbanHistory
from app.schemas.accounts import (
    FinancialAccountCreate,
    FinancialAccountOut,
    FinancialAccountUpdate,
    IbanHistoryCreate,
    IbanHistoryOut,
)
from app.services.currency_service import currency_exists
from app.services.transfer_recognition import archive_previous_iban, reapply_internal_transfer_detection

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _get_account_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> FinancialAccount:
    account = await db.get(FinancialAccount, account_id)
    # La RLS gia' impedisce di leggere righe di altri workspace (tornerebbero
    # None), ma il controllo esplicito sul workspace_id resta comunque il
    # primo livello di isolamento richiesto da SPEC §7 — non ci si affida
    # solo al database.
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


@router.post("", response_model=FinancialAccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: FinancialAccountCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
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
    # riporta gia' un bonifico verso di esso. UN SOLO commit a fine
    # richiesta (mai commit-poi-altre-query sulla stessa sessione: SET
    # LOCAL app.current_user_id scade al commit, vedi app/db/rls.py).
    if account.iban:
        await reapply_internal_transfer_detection(db, workspace_id)
    await db.commit()
    return account


@router.get("", response_model=list[FinancialAccountOut])
async def list_accounts(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[FinancialAccount]:
    result = await db.execute(
        select(FinancialAccount)
        .where(FinancialAccount.workspace_id == workspace_id)
        .order_by(FinancialAccount.created_at)
    )
    return list(result.scalars().all())


@router.get("/{account_id}", response_model=FinancialAccountOut)
async def get_account(
    account_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> FinancialAccount:
    return await _get_account_or_404(db, workspace_id, account_id)


@router.patch("/{account_id}", response_model=FinancialAccountOut)
async def update_account(
    account_id: uuid.UUID,
    payload: FinancialAccountUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> FinancialAccount:
    account = await _get_account_or_404(db, workspace_id, account_id)
    updates = payload.model_dump(exclude_unset=True)

    if "currency" in updates and not await currency_exists(db, workspace_id, updates["currency"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown currency code")

    # Milestone 09.5c: un istituto puo' cambiare l'IBAN di un conto pur
    # restando lo stesso conto (es. migrazione DE->IT osservata su Trade
    # Republic) — il valore VECCHIO va storicizzato PRIMA di sovrascriverlo,
    # altrimenti i bonifici storici che lo referenziano diventerebbero
    # irriconoscibili (vedi transfer_recognition.py).
    previous_iban = account.iban
    iban_changed = "iban" in updates and updates["iban"] != previous_iban

    for field, value in updates.items():
        setattr(account, field, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid bank reference") from exc

    if iban_changed and previous_iban:
        await archive_previous_iban(db, workspace_id, account.id, previous_iban)

    # Milestone 09.5b: stesso principio "salva e riapplica subito" di M09.5
    # — un IBAN nuovo/cambiato puo' rendere riconoscibili trasferimenti
    # interni gia' importati (SPEC §37). UN SOLO commit a fine richiesta,
    # stesso motivo di create_account sopra.
    if "iban" in updates and updates["iban"]:
        await reapply_internal_transfer_detection(db, workspace_id)
    await db.commit()
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    account = await _get_account_or_404(db, workspace_id, account_id)
    await db.delete(account)
    await db.commit()


# --- Storico IBAN (milestone 09.5c) -----------------------------------------
# Aggiunta MANUALE, distinta dalla storicizzazione automatica di
# update_account sopra: serve a chi imposta un conto per la prima volta
# conoscendo GIA' un IBAN precedente (es. un istituto che ha cambiato IBAN
# prima ancora che l'utente iniziasse a usare Lumio) — la storicizzazione
# automatica scatta solo quando il campo cambia DENTRO l'app, quindi non
# basterebbe da sola per questo caso.


@router.get("/{account_id}/iban-history", response_model=list[IbanHistoryOut])
async def list_iban_history(
    account_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[FinancialAccountIbanHistory]:
    await _get_account_or_404(db, workspace_id, account_id)
    result = await db.execute(
        select(FinancialAccountIbanHistory)
        .where(
            FinancialAccountIbanHistory.workspace_id == workspace_id,
            FinancialAccountIbanHistory.financial_account_id == account_id,
        )
        .order_by(FinancialAccountIbanHistory.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/{account_id}/iban-history", response_model=IbanHistoryOut, status_code=status.HTTP_201_CREATED
)
async def add_iban_history(
    account_id: uuid.UUID,
    payload: IbanHistoryCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> FinancialAccountIbanHistory:
    account = await _get_account_or_404(db, workspace_id, account_id)
    if payload.iban == account.iban:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "È già l'IBAN attuale del conto")
    entry = await archive_previous_iban(db, workspace_id, account_id, payload.iban)
    # Stesso principio "salva e riapplica subito" — un IBAN storico aggiunto
    # ora puo' rendere riconoscibili bonifici gia' importati (SPEC §37).
    await reapply_internal_transfer_detection(db, workspace_id)
    await db.commit()
    return entry


@router.delete("/{account_id}/iban-history/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_iban_history(
    account_id: uuid.UUID,
    history_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_account_or_404(db, workspace_id, account_id)
    entry = await db.get(FinancialAccountIbanHistory, history_id)
    if (
        entry is None
        or entry.workspace_id != workspace_id
        or entry.financial_account_id != account_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Historical IBAN not found")
    # Rimuove solo la voce storica: le transazioni gia' rimappate a
    # `transfer` grazie a questo IBAN restano com'erano (nessun rollback
    # automatico, stesso principio di M09.5).
    await db.delete(entry)
    await db.commit()

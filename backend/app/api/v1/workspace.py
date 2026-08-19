import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceOut, WorkspaceUpdate
from app.services.job_run_tracker import get_latest_run
from app.worker.queue import enqueue_market_data_refresh

router = APIRouter(prefix="/workspace", tags=["workspace"])


async def _get_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        # Non dovrebbe succedere (workspace_id viene da get_current_workspace_id,
        # gia' risolto da workspace_members) — 404 comunque onesto se capita.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return workspace


@router.get("", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    return await _get_workspace(db, workspace_id)


@router.patch("", response_model=WorkspaceOut)
async def update_workspace(
    payload: WorkspaceUpdate,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    """Sistema di valute: cambia solo `base_currency` (valuta di
    visualizzazione/aggregazione da questo momento in poi) — richiede la
    policy RLS UPDATE su `workspaces` (migration 0030, solo il proprietario:
    `is_workspace_owner`). Un membro non proprietario e' comunque visibile
    dalla SELECT (e' un membro) ma la UPDATE verrebbe filtrata dalla RLS
    (0 righe modificate, nessun errore dal DB) — controllato esplicitamente
    qui via `rowcount`, altrimenti l'endpoint risponderebbe 200 con
    l'impostazione INVARIATA invece di segnalare che non e' successo nulla."""
    workspace = await _get_workspace(db, workspace_id)
    new_currency = payload.base_currency.upper()
    currency_changed = new_currency != workspace.base_currency
    # Letto PRIMA del commit (mai dopo, stesso gotcha RLS del commento sotto:
    # `SET LOCAL app.current_user_id` scade al commit, e `job_runs` ha RLS).
    already_running = False
    if currency_changed:
        current_run = await get_latest_run(db, workspace_id, "market_data_refresh")
        already_running = current_run is not None and current_run.status == "running"
    try:
        result = await db.execute(
            sa_update(Workspace).where(Workspace.id == workspace_id).values(base_currency=new_currency)
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown currency code") from exc
    if result.rowcount == 0:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the workspace owner can change this setting")
    # NON un refresh dopo il commit (RLS gotcha noto: `SET LOCAL app.
    # current_user_id` scade al commit, una query successiva sulla stessa
    # sessione perderebbe l'identita' RLS — vedi upsert_manual_asset_price
    # in assets.py per lo stesso principio). L'UPDATE ORM-aware sopra
    # sincronizza gia' l'oggetto in sessione (strategia "evaluate" di
    # synchronize_session), nessuna query aggiuntiva necessaria.
    await db.commit()

    if currency_changed and not already_running:
        # Bug reale osservato: `fx_rates` ha sempre e solo tassi VERSO la
        # vecchia base_currency (es. USD->EUR, mai EUR->USD) — cambiando
        # base_currency, ogni dato nella vecchia valuta diventa "straniera
        # senza tasso disponibile" e sparisce da ogni totale (dashboard,
        # investimenti, entrate: TUTTO) finche' non arriva il refresh
        # schedulato del giorno dopo o l'utente clicca "Aggiorna ora" a
        # mano. Accodare qui lo stesso job del refresh manuale rende il
        # cambio di valuta utilizzabile da subito, senza intervento.
        await enqueue_market_data_refresh(workspace_id, user.id)

    return workspace

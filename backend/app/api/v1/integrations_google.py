import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id, set_rls_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.google import drive_client, oauth, sheets_client
from app.integrations.google.errors import GoogleAPIError, GoogleReauthRequiredError
from app.models.google_integration import GoogleIntegration
from app.models.user import User
from app.schemas.integrations_google import (
    ConnectUrlOut,
    ExportRequest,
    ExportTriggered,
    GoogleIntegrationOut,
    PickerTokenOut,
    SetDriveFolderRequest,
)
from app.schemas.job_runs import JobRunOut
from app.services import job_events
from app.services.audit_log_service import log_event
from app.services.google_integration_service import (
    disconnect,
    get_integration,
    get_picker_token_info,
    get_valid_access_token,
    save_new_integration,
    set_folder,
)
from app.services.job_run_tracker import get_latest_run
from app.worker.queue import enqueue_google_sheets_export

router = APIRouter(prefix="/integrations/google", tags=["integrations-google"])
logger = logging.getLogger("lumio.integrations.google")

JOB_KIND = "google_sheets_export"

# Tab creati subito al connect (SPEC_FE §50: lo spreadsheet esiste gia'
# "vuoto" prima del primo export) — stesso ordine usato da
# `report_builder.build_report` per i dati veri.
_INITIAL_SHEET_TITLES = ["Riepilogo", "Transazioni", "Entrate per Categoria", "Uscite per Categoria", "Portfolio"]


def _to_out(integration: GoogleIntegration) -> GoogleIntegrationOut:
    return GoogleIntegrationOut(
        google_account_email=integration.google_account_email,
        spreadsheet_url=integration.spreadsheet_url,
        drive_folder_name=integration.default_drive_folder_name,
        connected_at=integration.connected_at,
        last_exported_at=integration.last_exported_at,
    )


async def _get_integration_or_404(db: AsyncSession, workspace_id: uuid.UUID) -> GoogleIntegration:
    integration = await get_integration(db, workspace_id)
    if integration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessuna integrazione Google collegata")
    return integration


@router.get("", response_model=GoogleIntegrationOut | None)
async def get_google_integration(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> GoogleIntegrationOut | None:
    integration = await get_integration(db, workspace_id)
    return _to_out(integration) if integration else None


@router.get("/connect", response_model=ConnectUrlOut)
async def connect_google(
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> ConnectUrlOut:
    """Ritorna l'URL, non un redirect diretto: l'endpoint richiede bearer
    token (serve l'identita' per lo `state`), ma una navigazione reale del
    browser non porta l'header Authorization — il frontend naviga da solo
    su `authorize_url` dopo aver letto questa risposta (vedi
    `ConnectUrlOut`)."""
    state = oauth.build_state(workspace_id, user.id)
    return ConnectUrlOut(authorize_url=oauth.build_authorize_url(state))


@router.get("/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Nessun bearer token qui (redirect del browser da Google, non una
    chiamata autenticata dal frontend): l'identita' viaggia dentro `state`
    (JWT firmato, vedi `oauth.build_state`/`decode_state`), la RLS va
    impostata a mano invece che dalla dependency standard."""
    if error or not code or not state:
        return RedirectResponse(f"/settings/integrations?google_error={error or 'missing_code'}")

    decoded = oauth.decode_state(state)
    if decoded is None:
        return RedirectResponse("/settings/integrations?google_error=invalid_state")
    workspace_id, user_id = decoded
    await set_rls_current_user(db, user_id)

    try:
        credentials = await oauth.exchange_code(code)
        email = await oauth.fetch_account_email(credentials)
        spreadsheet_id, spreadsheet_url = await sheets_client.create_spreadsheet(
            credentials.access_token, "Lumio Finance", _INITIAL_SHEET_TITLES
        )
    except GoogleAPIError as exc:
        # Mai il token nel log (CLAUDE.md): il messaggio di GoogleAPIError
        # contiene solo status/corpo della risposta di Google, mai le
        # credenziali stesse.
        logger.warning("Connessione Google fallita per workspace %s: %s", workspace_id, exc)
        return RedirectResponse("/settings/integrations?google_error=connection_failed")

    existing = await get_integration(db, workspace_id)
    if existing is not None:
        # Riconnessione: la precedente riga viene sostituita (nuovo
        # spreadsheet, per non riusare un file legato a credenziali che
        # potrebbero essere gia' state revocate lato Google).
        await db.delete(existing)
        await db.flush()

    await save_new_integration(db, workspace_id, credentials, email, spreadsheet_id, spreadsheet_url)
    # save_new_integration ha gia' committato: SET LOCAL app.current_user_id
    # e' scaduto con quel commit (vedi app/db/rls.py), va rimpostato prima di
    # qualunque nuova query/INSERT RLS-dipendente sulla stessa sessione.
    await set_rls_current_user(db, user_id)
    await log_event(
        db, workspace_id, user_id, "GOOGLE_CONNECTED", entity_type="google_integration", entity_id=None
    )
    await db.commit()
    return RedirectResponse("/settings/integrations?connected=1&step=choose-folder")


@router.get("/picker-token", response_model=PickerTokenOut)
async def get_picker_token(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> PickerTokenOut:
    integration = await _get_integration_or_404(db, workspace_id)
    try:
        access_token, expires_in = await get_picker_token_info(db, integration)
    except GoogleReauthRequiredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return PickerTokenOut(access_token=access_token, expires_in_seconds=expires_in)


@router.post("/folder", response_model=GoogleIntegrationOut)
async def set_google_drive_folder(
    payload: SetDriveFolderRequest,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> GoogleIntegrationOut:
    integration = await _get_integration_or_404(db, workspace_id)
    try:
        access_token = await get_valid_access_token(db, integration)
        await drive_client.move_file_to_folder(access_token, integration.spreadsheet_id, payload.folder_id)
        folder_name = payload.folder_name
        if payload.folder_id and not folder_name:
            # Il Picker restituisce gia' il nome scelto: questo e' solo un
            # fallback difensivo se il frontend non lo passasse.
            folder_name = await drive_client.get_folder_name(access_token, payload.folder_id)
    except GoogleReauthRequiredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except GoogleAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    await set_folder(db, integration, payload.folder_id, folder_name)
    return _to_out(integration)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_google(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    integration = await _get_integration_or_404(db, workspace_id)
    await disconnect(db, integration)


@router.post("/export", response_model=ExportTriggered, status_code=status.HTTP_202_ACCEPTED)
async def trigger_google_export(
    payload: ExportRequest,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ExportTriggered:
    await _get_integration_or_404(db, workspace_id)
    # Stesso guard "gia' in corso" di trigger_market_data_refresh: al
    # massimo un export attivo per workspace ha senso (un solo spreadsheet
    # gestito), il doppio-click non deve accodare un secondo job.
    current = await get_latest_run(db, workspace_id, JOB_KIND)
    if current is not None and current.status == "running":
        return ExportTriggered(job_id=current.job_id or "")

    options = {
        "date_from": payload.date_from.isoformat(),
        "date_to": payload.date_to.isoformat(),
        "include_portfolio": payload.include_portfolio,
        "include_charts": payload.include_charts,
        "language": payload.language,
    }
    job_id = await enqueue_google_sheets_export(workspace_id, user.id, options)
    await log_event(
        db, workspace_id, user.id, "EXPORT_CREATED",
        entity_type="job", entity_id=None, metadata={"job_kind": JOB_KIND, "job_id": job_id},
    )
    await db.commit()
    return ExportTriggered(job_id=job_id)


@router.get("/export-status", response_model=JobRunOut | None)
async def get_google_export_status(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> JobRunOut | None:
    run = await get_latest_run(db, workspace_id, JOB_KIND)
    return JobRunOut.model_validate(run) if run else None


@router.get("/export-events")
async def stream_google_export_events(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> StreamingResponse:
    # Stesso pattern di `imports.py:stream_import_events` (fetch()+
    # ReadableStream lato frontend, non EventSource nativo: qui l'endpoint
    # resta comunque protetto da bearer token come ogni altro).
    return StreamingResponse(
        job_events.stream(
            workspace_id,
            namespace="google_export",
            timeout_seconds=get_settings().google_export_job_timeout_seconds,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

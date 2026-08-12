"""Logica DB-aware dell'integrazione Google Sheets di workspace (milestone
10), ponte tra l'API (`app/api/v1/integrations_google.py`)/il job async
(`app/worker/jobs/google_export_job.py`) e i client REST puri
`app/integrations/google/{oauth,sheets_client,drive_client}.py` (che non
toccano mai il DB). Stessa separazione di `ai_profile_service.py`/
`market_data_profile_service.py`, con una differenza: qui c'e' AL MASSIMO
UNA riga per workspace (vedi `GoogleIntegration`, non una lista di profili).
"""
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret
from app.integrations.google.errors import GoogleAPIError, GoogleReauthRequiredError
from app.integrations.google.oauth import GoogleCredentials, get_valid_credentials, revoke
from app.models.google_integration import GoogleIntegration

logger = logging.getLogger("lumio.integrations.google")


async def get_integration(db: AsyncSession, workspace_id: uuid.UUID) -> GoogleIntegration | None:
    result = await db.execute(
        select(GoogleIntegration).where(GoogleIntegration.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


def _load_credentials(integration: GoogleIntegration) -> GoogleCredentials:
    decrypted = decrypt_secret(integration.credentials_encrypted)
    if decrypted is None:
        # Non dovrebbe succedere (stessa SECRET_KEY che ha cifrato il blob),
        # ma se capita e' uno stato non recuperabile: tratta come "serve
        # riconnessione" invece di far esplodere il chiamante con un errore
        # di parsing poco chiaro.
        raise GoogleReauthRequiredError("Credenziali Google non decifrabili: e' necessario riconnettersi")
    return GoogleCredentials.from_json(decrypted)


async def _ensure_valid_credentials(db: AsyncSession, integration: GoogleIntegration) -> GoogleCredentials:
    """Rinnova le credenziali se scadute e persiste il risultato — nucleo
    condiviso da `get_valid_access_token` (che serve solo il token) e da
    `get_picker_token_info` (che serve anche la scadenza).

    Commit immediato SOLO se il token e' stato rinnovato (non ad ogni
    chiamata): a differenza degli altri service DB-aware del progetto (dove
    il commit resta responsabilita' del router), qui e' necessario perche'
    questa funzione e' chiamata sia da endpoint API sia dal job worker
    asincrono, e un access_token rinnovato ma non persistito verrebbe perso
    alla chiamata successiva, forzando un refresh ad ogni singola richiesta
    verso Google (oltre a rischiare due refresh concorrenti che invalidano
    il token dell'altro).

    Se il refresh_token non e' piu' valido (`GoogleReauthRequiredError`),
    l'integrazione viene eliminata: l'accesso e' stato revocato lato Google,
    tenere la riga non farebbe che ripetere lo stesso errore ad ogni export.
    """
    credentials = _load_credentials(integration)
    try:
        refreshed = await get_valid_credentials(credentials)
    except GoogleReauthRequiredError:
        await db.delete(integration)
        await db.commit()
        raise

    if refreshed.access_token != credentials.access_token:
        integration.credentials_encrypted = encrypt_secret(refreshed.to_json())
        await db.commit()
    return refreshed


async def get_valid_access_token(db: AsyncSession, integration: GoogleIntegration) -> str:
    credentials = await _ensure_valid_credentials(db, integration)
    return credentials.access_token


async def get_picker_token_info(db: AsyncSession, integration: GoogleIntegration) -> tuple[str, int]:
    """Ritorna `(access_token, secondi alla scadenza)` per il widget Google
    Picker lato frontend (vedi `PickerTokenOut`) — l'unico consumer che ha
    bisogno di sapere anche la scadenza, non solo il token."""
    credentials = await _ensure_valid_credentials(db, integration)
    remaining = max(0, int(credentials.expires_at - time.time()))
    return credentials.access_token, remaining


async def save_new_integration(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    credentials: GoogleCredentials,
    google_account_email: str,
    spreadsheet_id: str,
    spreadsheet_url: str,
) -> GoogleIntegration:
    integration = GoogleIntegration(
        workspace_id=workspace_id,
        google_account_email=google_account_email,
        credentials_encrypted=encrypt_secret(credentials.to_json()),
        spreadsheet_id=spreadsheet_id,
        spreadsheet_url=spreadsheet_url,
    )
    db.add(integration)
    await db.commit()
    return integration


async def set_folder(
    db: AsyncSession, integration: GoogleIntegration, folder_id: str | None, folder_name: str | None
) -> None:
    integration.default_drive_folder_id = folder_id
    integration.default_drive_folder_name = folder_name
    await db.commit()


async def mark_exported(db: AsyncSession, integration: GoogleIntegration) -> None:
    integration.last_exported_at = datetime.now(timezone.utc)
    await db.commit()


async def disconnect(db: AsyncSession, integration: GoogleIntegration) -> None:
    """Revoca il token presso Google (best-effort) e rimuove sempre la riga:
    l'utente ha chiesto di disconnettersi da Lumio, un problema nel
    raggiungere Google (rete, credenziali gia' invalide) non deve impedirlo
    — resterebbe altrimenti "connesso" in UI senza modo di uscirne."""
    try:
        credentials = _load_credentials(integration)
        await revoke(credentials)
    except GoogleAPIError as exc:
        logger.warning("Revoca token Google non riuscita, si procede comunque: %s", exc)
    await db.delete(integration)
    await db.commit()

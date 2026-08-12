"""Client OAuth2 Google (Authorization Code, web app "confidential client")
via httpx REST diretto — stesso pattern di `app/marketdata/providers/yahoo.py`
(niente `google-auth`/`google-api-python-client`: il flusso e' poche POST
form-encoded, non giustifica una dipendenza sync-first in un codebase
async-nativo).

Scope minimo `drive.file` (+`openid email` solo per mostrare "connesso
come..." in UI, mai per leggere altro): Lumio vede/scrive SOLO i file che
crea lei stessa, mai spreadsheet preesistenti dell'utente — basta anche
per scrivere contenuto/formattazione/grafici sul file appena creato via
Sheets API, non serve lo scope "spreadsheets" separato.

Questo modulo non tocca mai il DB: chi lo chiama (vedi
`app/services/google_integration_service.py`) e' responsabile di
cifrare/persistere `GoogleCredentials` dopo un refresh.
"""
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import get_settings
from app.core.security import JWT_ALGORITHM
from app.integrations.google.errors import GoogleAPIError, GoogleReauthRequiredError

_STATE_PURPOSE = "google_oauth_state"
_STATE_TTL_MINUTES = 10

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE = "https://www.googleapis.com/auth/drive.file openid email"
_TIMEOUT = 15.0
# Margine di sicurezza prima della scadenza reale dichiarata da Google: un
# export non deve fallire a meta' perche' il token e' scaduto tra l'inizio
# e la fine del job.
_EXPIRY_SAFETY_MARGIN_SECONDS = 60


@dataclass
class GoogleCredentials:
    access_token: str
    refresh_token: str
    expires_at: float  # epoch seconds
    scope: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
                "scope": self.scope,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "GoogleCredentials":
        data = json.loads(raw)
        return cls(**data)

    @property
    def is_expired(self) -> bool:
        return time.time() >= (self.expires_at - _EXPIRY_SAFETY_MARGIN_SECONDS)


def build_state(workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """`state` OAuth = un JWT a vita brevissima (10 minuti, il tempo di
    completare il consenso su Google) firmato con la stessa `SECRET_KEY`
    gia' usata per gli access token (`app/core/security.py`) — CSRF
    protection sul callback senza bisogno di una sessione/cookie dedicata:
    il callback non riceve altro contesto se non questo parametro."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "purpose": _STATE_PURPOSE,
        "workspace_id": str(workspace_id),
        "user_id": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=_STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_state(state: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Ritorna `(workspace_id, user_id)` se `state` e' un token valido e non
    scaduto emesso da `build_state`, altrimenti `None` (mai un'eccezione:
    un `state` non valido/scaduto e' un normale 400, non un errore
    inatteso)."""
    settings = get_settings()
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _STATE_PURPOSE:
        return None
    try:
        return uuid.UUID(payload["workspace_id"]), uuid.UUID(payload["user_id"])
    except (KeyError, ValueError):
        return None


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        # access_type=offline + prompt=consent: necessari per ottenere SEMPRE
        # un refresh_token, anche se l'utente ha gia' autorizzato Lumio in
        # passato (altrimenti Google puo' ometterlo nelle richieste successive).
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> GoogleCredentials:
    settings = get_settings()
    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(TOKEN_URL, data=data)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Scambio codice OAuth Google fallito: {exc}") from exc

    body = response.json()
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        # Non dovrebbe capitare (forziamo sempre prompt=consent sopra), ma
        # niente credenziali inutilizzabili in silenzio se Google lo omette
        # comunque: l'utente deve poter riprovare la connessione.
        raise GoogleAPIError("Google non ha restituito un refresh_token: riprova a connetterti")
    return GoogleCredentials(
        access_token=body["access_token"],
        refresh_token=refresh_token,
        expires_at=time.time() + body["expires_in"],
        scope=body.get("scope", SCOPE),
    )


async def refresh_access_token(credentials: GoogleCredentials) -> GoogleCredentials:
    settings = get_settings()
    data = {
        "refresh_token": credentials.refresh_token,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.post(TOKEN_URL, data=data)
        except httpx.HTTPError as exc:
            raise GoogleAPIError(f"Rinnovo token Google fallito: {exc}") from exc

    if response.status_code == 400 and response.json().get("error") == "invalid_grant":
        raise GoogleReauthRequiredError(
            "L'accesso a Google e' stato revocato o e' scaduto: e' necessario riconnettersi"
        )
    try:
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Rinnovo token Google fallito: {exc}") from exc

    body = response.json()
    return GoogleCredentials(
        access_token=body["access_token"],
        refresh_token=credentials.refresh_token,  # Google non lo re-include mai qui
        expires_at=time.time() + body["expires_in"],
        scope=body.get("scope", credentials.scope),
    )


async def get_valid_credentials(credentials: GoogleCredentials) -> GoogleCredentials:
    """Ritorna `credentials` invariate se l'access_token e' ancora valido,
    altrimenti il risultato di un refresh. Chi chiama deve persistere il
    risultato se e' cambiato (confronto per identita' non basta, confrontare
    `access_token`)."""
    if not credentials.is_expired:
        return credentials
    return await refresh_access_token(credentials)


async def revoke(credentials: GoogleCredentials) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.post(REVOKE_URL, data={"token": credentials.refresh_token})
        except httpx.HTTPError as exc:
            raise GoogleAPIError(f"Revoca token Google fallita: {exc}") from exc
    # Google risponde 200 anche se il token era gia' invalido/scaduto
    # (operazione idempotente) - solo un errore server-side e' un problema
    # reale da segnalare, mai un motivo per bloccare la disconnessione lato
    # Lumio (la riga va comunque eliminata).
    if response.status_code >= 500:
        raise GoogleAPIError(f"Revoca token Google fallita: HTTP {response.status_code}")


async def fetch_account_email(credentials: GoogleCredentials) -> str:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {credentials.access_token}"}
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GoogleAPIError(f"Lettura profilo Google fallita: {exc}") from exc
    return response.json().get("email", "")

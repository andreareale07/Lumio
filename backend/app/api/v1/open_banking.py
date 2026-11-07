"""Open Banking (connettore Enable Banking) — montato solo con
`OPEN_BANKING_ENABLED=true` (vedi `app/api/v1/router.py`).

Le credenziali (application ID + chiave privata) sono PER UTENTE: i Terms di
Enable Banking permettono l'uso gratuito solo per conti propri di persone
fisiche. Nessun token o segreto lascia mai il server: il browser riceve solo
l'URL di autorizzazione della banca e, dopo il callback, un redirect.
"""
import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id, set_rls_current_user
from app.core.client_info import clean_user_agent, client_ip
from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.financial_account import FinancialAccount
from app.models.open_banking import BankConnection, BankConnectionAccount
from app.models.user import User
from app.openbanking import logos as ob_logos
from app.openbanking import state as ob_state
from app.openbanking.errors import (
    OpenBankingAuthError,
    OpenBankingError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.schemas.open_banking import (
    AccountUpdateIn,
    ApplicationIdIn,
    ConnectionAccountOut,
    ConnectionOut,
    ConnectUrlOut,
    CredentialOut,
    DisconnectResultOut,
    InstitutionOut,
    OpenBankingStatusOut,
    StartConnectionIn,
    SyncQueuedOut,
)
from app.services import bank_sync_service, open_banking_service
from app.services.audit_log_service import log_event
from app.worker.queue import enqueue_bank_sync

router = APIRouter(prefix="/open-banking", tags=["open-banking"])
logger = logging.getLogger("lumio.open_banking")

_FRONTEND_PAGE = "/settings/bank-connections"
_CALLBACK_RATE_LIMIT = "30/minute"
# Ogni chiamata a /institutions e' una richiesta firmata al provider esterno.
_INSTITUTIONS_RATE_LIMIT = "30/minute"
_DISCONNECT_LOCK_TTL_SECONDS = 120
_LOGO_RATE_LIMIT = "300/minute"
_LOGO_KEY_RE = re.compile(r"^[0-9a-f]{32}$")


def _http_error(exc: OpenBankingError) -> HTTPException:
    if isinstance(exc, OpenBankingAuthError):
        return HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Enable Banking ha rifiutato le credenziali: controlla l'application ID e il certificato caricato",
        )
    if isinstance(exc, RateLimitedError):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Troppe richieste alla banca: riprova piu' tardi")
    if isinstance(exc, ProviderUnavailableError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Servizio Open Banking temporaneamente non disponibile")
    if exc.code in ("not_configured", "key_unreadable"):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "Errore del servizio Open Banking")


def _credential_out(credential) -> CredentialOut:
    return CredentialOut(
        provider=credential.provider,
        configured=bool(credential.application_id),
        application_id=credential.application_id,
        certificate_pem=credential.certificate_pem,
        created_at=credential.created_at,
    )


async def _require_credential(db: AsyncSession, user: User):
    credential = await open_banking_service.get_credential(db, user.id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Credenziali Open Banking non configurate")
    return credential


def _connection_out(
    connection: BankConnection, accounts: list[BankConnectionAccount], sync_running: bool
) -> ConnectionOut:
    now = datetime.now(UTC)
    days_left = None
    if connection.valid_until is not None:
        days_left = (connection.valid_until - now).days
    effective_status = connection.status
    if connection.status == "active" and days_left is not None and connection.valid_until <= now:
        effective_status = "expired"
    return ConnectionOut(
        id=connection.id,
        aspsp_name=connection.aspsp_name,
        aspsp_country=connection.aspsp_country,
        status=effective_status,
        valid_until=connection.valid_until,
        days_until_expiry=days_left,
        expiring_soon=effective_status == "active"
        and days_left is not None
        and days_left < open_banking_service.EXPIRING_SOON_DAYS,
        last_sync_at=connection.last_sync_at,
        last_error=connection.last_error,
        sync_running=sync_running,
        accounts=[
            ConnectionAccountOut(
                id=a.id,
                name=a.name,
                product=a.product,
                iban_masked=open_banking_service.mask_iban(a.iban),
                currency=a.currency,
                enabled=a.enabled,
                financial_account_id=a.financial_account_id,
                last_sync_at=a.last_sync_at,
                transactions_imported=a.transactions_imported,
            )
            for a in accounts
        ],
    )


# ---- stato e credenziali -------------------------------------------------


@router.get("", response_model=OpenBankingStatusOut)
async def get_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> OpenBankingStatusOut:
    redirect_uri = get_settings().open_banking_redirect_uri
    credential = await open_banking_service.get_credential(db, user.id)
    return OpenBankingStatusOut(
        redirect_uri=redirect_uri,
        redirect_uri_configured=bool(redirect_uri),
        credential=_credential_out(credential) if credential else None,
    )


@router.post("/credentials", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
async def generate_credentials(
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> CredentialOut:
    """Genera la coppia di chiavi: la privata resta cifrata sul server, la
    risposta contiene solo il certificato da caricare sul Control Panel."""
    if await open_banking_service.get_credential(db, user.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Credenziali gia' generate")
    credential = await open_banking_service.create_credential(db, workspace_id, user.id)
    out = _credential_out(credential)
    await db.commit()
    return out


@router.put("/credentials/application-id", response_model=CredentialOut)
async def set_application_id(
    payload: ApplicationIdIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CredentialOut:
    credential = await _require_credential(db, user)
    credential.application_id = payload.application_id
    await db.flush()
    out = _credential_out(credential)
    await db.commit()
    return out


@router.delete("/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credentials(
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoca le sessioni presso il provider (best effort) e cancella
    credenziali, connessioni e conti. I movimenti gia' importati restano."""
    credential = await _require_credential(db, user)
    await open_banking_service.delete_credential(db, credential)
    await log_event(db, workspace_id, user.id, "BANK_DISCONNECTED", entity_type="open_banking_credential")
    await db.commit()


# ---- banche e connessioni -------------------------------------------------


@router.get("/institutions", response_model=list[InstitutionOut])
@limiter.limit(_INSTITUTIONS_RATE_LIMIT)
async def list_institutions(
    request: Request, country: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[InstitutionOut]:
    if len(country) != 2 or not country.isalpha():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Codice paese non valido")
    credential = await _require_credential(db, user)
    try:
        connector = open_banking_service.build_connector(credential)
        institutions = await connector.list_institutions(country.upper())
    except OpenBankingError as exc:
        raise _http_error(exc) from exc
    # Il browser non contatta il sito dei loghi: riceve un percorso locale (proxy).
    logo_paths = await ob_logos.register_logos(sorted({i.logo_url for i in institutions if i.logo_url}))
    return [
        InstitutionOut(
            name=i.name,
            country=i.country,
            logo_url=logo_paths.get(i.logo_url) if i.logo_url else None,
            beta=i.beta,
            maximum_consent_validity_days=(
                i.maximum_consent_validity_seconds // 86400 if i.maximum_consent_validity_seconds else None
            ),
        )
        for i in institutions
        if not i.psu_types or "personal" in i.psu_types
    ]


@router.get("/logos/{key}")
@limiter.limit(_LOGO_RATE_LIMIT)
async def bank_logo(request: Request, key: str) -> Response:
    """Logo di una banca servito dalla nostra origine (vedi `openbanking/logos.py`).
    Senza autenticazione perche' lo richiede un `<img>`; serve solo chiavi
    opache registrate da un elenco banche, mai un URL dato dal chiamante."""
    if not _LOGO_KEY_RE.match(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo non trovato")
    logo = await ob_logos.get_logo(key)
    if logo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo non trovato")
    data, content_type = logo
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )


@router.post("/connections", response_model=ConnectUrlOut)
async def start_connection(
    payload: StartConnectionIn,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ConnectUrlOut:
    """Avvia l'autorizzazione: ritorna l'URL (non un redirect: la richiesta
    porta il bearer, una navigazione del browser no) verso cui il frontend
    porta l'utente. Le credenziali bancarie si inseriscono solo sulla pagina
    della banca, mai in Lumio."""
    redirect_uri = get_settings().open_banking_redirect_uri
    if not redirect_uri:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OPEN_BANKING_REDIRECT_URI non configurato")
    credential = await _require_credential(db, user)
    try:
        connector = open_banking_service.build_connector(credential)
        institutions = await connector.list_institutions(payload.aspsp_country.upper())
        institution = next((i for i in institutions if i.name == payload.aspsp_name), None)
        if institution is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Banca non disponibile")

        await open_banking_service.purge_stale_pending(db, user.id)
        nonce = ob_state.new_nonce()
        connection = BankConnection(
            workspace_id=workspace_id,
            owner_user_id=user.id,
            credential_id=credential.id,
            provider=credential.provider,
            aspsp_name=institution.name,
            aspsp_country=institution.country,
            psu_type=payload.psu_type,
            status="pending",
            state_nonce_hash=ob_state.hash_nonce(nonce),
        )
        db.add(connection)
        await db.flush()

        start = await connector.start_authorization(
            institution.name,
            institution.country,
            redirect_url=redirect_uri,
            state=ob_state.build_state(workspace_id, user.id, connection.id, nonce),
            valid_until=open_banking_service.consent_valid_until(institution.maximum_consent_validity_seconds),
            psu_type=payload.psu_type,
        )
    except OpenBankingError as exc:
        await db.rollback()
        raise _http_error(exc) from exc
    connection.authorization_id = start.authorization_id
    await db.commit()
    return ConnectUrlOut(authorize_url=start.url)


@router.get("/callback")
@limiter.limit(_CALLBACK_RATE_LIMIT)
async def authorization_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Redirect del browser dalla banca. Nessun bearer: l'identita' viaggia nello
    `state` (JWT firmato, valido 10 minuti) e il nonce in esso contenuto e'
    MONOUSO (confrontato con l'impronta salvata sulla connessione e azzerato
    qui). Gli errori tornano al frontend come codici generici."""
    decoded = ob_state.decode_state(state) if state else None
    if decoded is None:
        return RedirectResponse(f"{_FRONTEND_PAGE}?error=invalid_state")

    await set_rls_current_user(db, decoded.user_id)
    # Il nonce si consuma in modo ATOMICO, qualunque sia l'esito: un solo
    # UPDATE condizionale con RETURNING. Due callback concorrenti con lo stesso
    # `state` si serializzano sul blocco di riga e il secondo, rivalutando la
    # condizione dopo il commit del primo, non trova piu' il nonce.
    claimed = await db.scalar(
        update(BankConnection)
        .where(
            BankConnection.id == decoded.connection_id,
            BankConnection.owner_user_id == decoded.user_id,
            BankConnection.status == "pending",
            BankConnection.state_nonce_hash == ob_state.hash_nonce(decoded.nonce),
        )
        .values(state_nonce_hash=None)
        .returning(BankConnection.id)
    )
    if claimed is None:
        return RedirectResponse(f"{_FRONTEND_PAGE}?error=invalid_state")
    connection = await open_banking_service.get_connection(db, decoded.user_id, decoded.connection_id)
    if connection is None:
        return RedirectResponse(f"{_FRONTEND_PAGE}?error=invalid_state")

    if error or not code:
        connection.status = "error"
        connection.last_error = "authorization_denied"
        await db.commit()
        return RedirectResponse(f"{_FRONTEND_PAGE}?error=authorization_denied")

    credential = await open_banking_service.get_credential(db, decoded.user_id)
    try:
        if credential is None:
            raise OpenBankingError("Credenziali assenti", code="not_configured")
        connector = open_banking_service.build_connector(credential)
        session = await connector.complete_authorization(code)
        await open_banking_service.apply_session(
            db, connection, session, encrypt_secret(session.session_id)
        )
        await open_banking_service.retire_previous_connections(db, connection, connector)
    except OpenBankingError as exc:
        # Mai il corpo della risposta nel log: solo codice e stato.
        logger.warning("Callback Open Banking fallito (%s, http=%s)", exc.code, exc.http_status)
        connection.status = "error"
        connection.last_error = "authorization_failed"
        await db.commit()
        return RedirectResponse(f"{_FRONTEND_PAGE}?error=authorization_failed")

    await log_event(
        db,
        decoded.workspace_id,
        decoded.user_id,
        "BANK_CONNECTED",
        entity_type="bank_connection",
        entity_id=connection.id,
    )
    await db.commit()
    return RedirectResponse(f"{_FRONTEND_PAGE}?connected={connection.id}")


@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ConnectionOut]:
    connections = await open_banking_service.list_connections(db, user.id)
    accounts = await open_banking_service.list_connection_accounts(db, user.id, [c.id for c in connections])
    result = []
    for connection in connections:
        running = await bank_sync_service.is_sync_running(connection.id)
        result.append(_connection_out(connection, accounts[connection.id], running))
    return result


@router.patch("/connections/{connection_id}/accounts/{account_id}", response_model=ConnectionAccountOut)
async def update_connection_account(
    connection_id: uuid.UUID,
    account_id: uuid.UUID,
    payload: AccountUpdateIn,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ConnectionAccountOut:
    connection = await open_banking_service.get_connection(db, user.id, connection_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connessione non trovata")
    account = next(
        (a for a in await open_banking_service.list_accounts_of(db, connection.id) if a.id == account_id), None
    )
    if account is None or account.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conto non trovato")

    if payload.create_account and payload.financial_account_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scegli un conto esistente oppure creane uno")

    if payload.create_account:
        lumio_account = await open_banking_service.create_lumio_account_from_bank_account(
            db, workspace_id, connection, account
        )
        account.financial_account_id = lumio_account.id
    elif payload.financial_account_id is not None:
        # Doppio livello: la RLS filtra per workspace, il controllo esplicito lo
        # rende evidente e produce un 404 invece di un errore di FK.
        target = await db.scalar(
            select(FinancialAccount).where(
                FinancialAccount.id == payload.financial_account_id,
                FinancialAccount.workspace_id == workspace_id,
            )
        )
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conto Lumio non trovato")
        account.financial_account_id = target.id

    if payload.enabled is not None:
        if payload.enabled and account.financial_account_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Abbina il conto a un conto Lumio prima di attivarlo"
            )
        account.enabled = payload.enabled

    await db.flush()
    out = ConnectionAccountOut(
        id=account.id,
        name=account.name,
        product=account.product,
        iban_masked=open_banking_service.mask_iban(account.iban),
        currency=account.currency,
        enabled=account.enabled,
        financial_account_id=account.financial_account_id,
        last_sync_at=account.last_sync_at,
        transactions_imported=account.transactions_imported,
    )
    await db.commit()
    return out


@router.post("/connections/{connection_id}/sync", response_model=SyncQueuedOut, status_code=status.HTTP_202_ACCEPTED)
async def sync_connection(
    connection_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncQueuedOut:
    connection = await open_banking_service.get_connection(db, user.id, connection_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connessione non trovata")
    if connection.status != "active" or (connection.valid_until and connection.valid_until <= datetime.now(UTC)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Autorizzazione scaduta: ricollega la banca")
    accounts = await open_banking_service.list_accounts_of(db, connection.id)
    if not any(a.enabled and a.financial_account_id for a in accounts):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nessun conto attivo da sincronizzare")
    if await bank_sync_service.is_sync_running(connection.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Sincronizzazione gia' in corso")

    if not await bank_sync_service.try_start_manual_sync(connection.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Attendi qualche secondo prima di sincronizzare di nuovo")

    # Nessun `_job_id` fisso (arq ignorerebbe i rilanci per un'ora): il doppio
    # click e' coperto dal lock Redis e dalla pausa minima controllati sopra.
    await enqueue_bank_sync(
        connection.id,
        user.id,
        psu_ip=client_ip(request),
        psu_user_agent=clean_user_agent(request.headers.get("user-agent")),
    )
    return SyncQueuedOut()


@router.delete("/connections/{connection_id}", response_model=DisconnectResultOut)
async def disconnect(
    connection_id: uuid.UUID,
    delete_data: bool = False,
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DisconnectResultOut:
    """Scollega la banca: revoca il consenso presso il provider (best effort) e
    cancella sessione e conti collegati. I movimenti gia' importati restano,
    salvo `delete_data=true`: in quel caso si eliminano anche quelli importati
    da questa banca (mai PDF/CSV o inseriti a mano)."""
    connection = await open_banking_service.get_connection(db, user.id, connection_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connessione non trovata")

    # Lo stesso lock della sincronizzazione: se una sync e' in corso (ha gia'
    # scaricato i movimenti ma non li ha ancora scritti) la cancellazione
    # perderebbe la corsa e i dati tornerebbero. Il lock resta preso fino al
    # commit, cosi' nessuna sync parte a meta' scollegamento.
    if not await bank_sync_service.try_acquire_lock(connection.id, ttl=_DISCONNECT_LOCK_TTL_SECONDS):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Sincronizzazione in corso: attendi il completamento e riprova"
        )
    try:
        # Prima i controlli che possono rifiutare (409), poi gli effetti esterni:
        # nessuna revoca presso la banca se poi l'eliminazione dei dati non parte.
        deleted = 0
        if delete_data:
            deleted = await open_banking_service.delete_connection_imported_data(db, workspace_id, connection)

        revoked = True
        credential = await open_banking_service.get_credential(db, user.id)
        if credential is not None and connection.session_id_encrypted:
            try:
                connector = open_banking_service.build_connector(credential)
            except OpenBankingError:
                revoked = False
            else:
                revoked = await open_banking_service.revoke_connection_session(connection, connector)
        await db.delete(connection)
        await log_event(
            db,
            workspace_id,
            user.id,
            "BANK_DISCONNECTED",
            entity_type="bank_connection",
            entity_id=connection_id,
            metadata={"deleted_transactions_count": deleted} if delete_data else None,
        )
        await db.commit()
    finally:
        await bank_sync_service.release_lock(connection_id)
    return DisconnectResultOut(deleted_transactions=deleted, revoked_at_bank=revoked)

import uuid

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_primary_workspace_id, set_rls_current_user
from app.core.config import get_settings
from app.core.rate_limit import LOGIN_RATE_LIMIT, REFRESH_RATE_LIMIT, REGISTER_RATE_LIMIT, limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    TotpDisableRequest,
    TotpEnableRequest,
    TotpSetupResponse,
    UserOut,
)
from app.services.analytics import resolve_currency
from app.services import totp as totp_service
from app.services.audit_log_service import log_event
from app.services.session import (
    create_refresh_token,
    get_user_id_for_refresh_token,
    revoke_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
# Il guscio nativo (Capacitor) non puo' usare il cookie di refresh: SameSite=strict
# non viaggia dal WebView (origin diversa dal server). Si identifica con questo
# header e riceve/restituisce il refresh token nel body.
NATIVE_CLIENT_HEADER = "x-lumio-client"

# Hash "innocuo" precalcolato: usato per far girare verify_password() anche
# quando l'email non esiste, cosi' la risposta ad un login con email
# inesistente impiega un tempo comparabile a quella con password sbagliata
# (mitiga l'enumerazione utenti via timing).
_DUMMY_PASSWORD_HASH = hash_password(str(uuid.uuid4()))


def _is_native_client(request: Request) -> bool:
    return request.headers.get(NATIVE_CLIENT_HEADER, "").lower() == "native"


def _deliver_refresh_token(
    request: Request, response: Response, token_response: TokenResponse, token: str
) -> None:
    """Cookie httpOnly per il web, body (-> Keystore) per l'app nativa."""
    if _is_native_client(request):
        token_response.refresh_token = token
    else:
        _set_refresh_cookie(response, token)


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
    )


async def _build_token_response(db: AsyncSession, user: User) -> TokenResponse:
    await set_rls_current_user(db, user.id)
    workspace_id = await get_primary_workspace_id(db, user.id)
    if workspace_id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "User has no workspace")

    access_token = create_access_token(user.id)
    return TokenResponse(
        access_token=access_token,
        user=MeResponse(
            **UserOut.model_validate(user).model_dump(),
            workspace_id=workspace_id,
            google_enabled=get_settings().google_enabled,
            open_banking_enabled=get_settings().open_banking_enabled,
            base_currency=await resolve_currency(db, workspace_id),
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(REGISTER_RATE_LIMIT)
async def register(
    request: Request, payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)

    try:
        # flush(), non solo commit(): l'INSERT (con RETURNING) parte subito,
        # quindi la UniqueViolation sull'email duplicata arriva qui, non al
        # commit finale.
        await db.flush()

        await set_rls_current_user(db, user.id)

        workspace = Workspace(name="Personale", owner_user_id=user.id)
        db.add(workspace)
        await db.flush()

        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from exc

    access_token = create_access_token(user.id)
    refresh_token = await create_refresh_token(user.id)

    token_response = TokenResponse(
        access_token=access_token,
        user=MeResponse(
            **UserOut.model_validate(user).model_dump(),
            workspace_id=workspace.id,
            google_enabled=get_settings().google_enabled,
            open_banking_enabled=get_settings().open_banking_enabled,
            base_currency=workspace.base_currency,
        ),
    )
    _deliver_refresh_token(request, response, token_response, refresh_token)
    return token_response


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(
    request: Request, payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))

    if user is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    # Seconda verifica, solo DOPO la password corretta (la risposta non rivela
    # se un'email esiste): con 2FA attiva il codice e' obbligatorio.
    if user.totp_enabled:
        if not payload.totp_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "TOTP_REQUIRED")
        if not await totp_service.verify_code(user, payload.totp_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "TOTP_INVALID")

    token_response = await _build_token_response(db, user)
    await log_event(
        db, token_response.user.workspace_id, user.id, "LOGIN", entity_type="user", entity_id=user.id
    )
    await db.commit()
    refresh_token = await create_refresh_token(user.id)
    _deliver_refresh_token(request, response, token_response, refresh_token)
    return token_response


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(REFRESH_RATE_LIMIT)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None),
    payload: RefreshRequest | None = Body(default=None),
) -> TokenResponse:
    # Client nativo: il token arriva nel body (nessun cookie nel WebView).
    if _is_native_client(request) and payload is not None:
        refresh_token = payload.refresh_token
    if refresh_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")

    user_id = await get_user_id_for_refresh_token(refresh_token)
    # Rotazione: il token usato muore comunque, valido o non piu' valido.
    await revoke_refresh_token(refresh_token)

    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    token_response = await _build_token_response(db, user)
    new_refresh_token = await create_refresh_token(user.id)
    _deliver_refresh_token(request, response, token_response, new_refresh_token)
    return token_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    payload: RefreshRequest | None = Body(default=None),
) -> None:
    if _is_native_client(request) and payload is not None:
        refresh_token = payload.refresh_token
    if refresh_token is not None:
        await revoke_refresh_token(refresh_token)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    workspace_id = await get_primary_workspace_id(db, user.id)
    if workspace_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No workspace found for user")
    return MeResponse(
        **UserOut.model_validate(user).model_dump(),
        workspace_id=workspace_id,
        google_enabled=get_settings().google_enabled,
        open_banking_enabled=get_settings().open_banking_enabled,
        base_currency=await resolve_currency(db, workspace_id),
    )


# 400 (non 401) sugli errori di codice/password: un 401 farebbe tentare al client
# un refresh della sessione e poi la disconnessione, per un semplice errore di digitazione.
@router.post("/totp/setup", response_model=TotpSetupResponse)
@limiter.limit(LOGIN_RATE_LIMIT)
async def totp_setup(
    request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> TotpSetupResponse:
    """Avvia l'attivazione: genera un segreto in attesa (2FA ancora spenta).
    Richiamarlo prima di `enable` sostituisce il segreto in attesa."""
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "2FA already enabled")
    secret = totp_service.new_secret()
    user.totp_secret_encrypted = totp_service.encrypt_totp_secret(secret)
    await db.commit()
    return TotpSetupResponse(secret=secret, otpauth_uri=totp_service.provisioning_uri(secret, user.email))


@router.post("/totp/enable", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(LOGIN_RATE_LIMIT)
async def totp_enable(
    request: Request,
    payload: TotpEnableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "2FA already enabled")
    if not user.totp_secret_encrypted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Run setup first")
    if not await totp_service.verify_code(user, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOTP_INVALID")
    user.totp_enabled = True
    await db.commit()


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(LOGIN_RATE_LIMIT)
async def totp_disable(
    request: Request,
    payload: TotpDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Spegne la 2FA: servono password E codice, cosi' un access token rubato
    non basta a toglierla."""
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "2FA not enabled")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid password")
    if not await totp_service.verify_code(user, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOTP_INVALID")
    user.totp_enabled = False
    user.totp_secret_encrypted = None
    await db.commit()

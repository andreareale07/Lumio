import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_primary_workspace_id, set_rls_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse, UserOut
from app.services.session import (
    create_refresh_token,
    get_user_id_for_refresh_token,
    revoke_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

# Hash "innocuo" precalcolato: usato per far girare verify_password() anche
# quando l'email non esiste, cosi' la risposta ad un login con email
# inesistente impiega un tempo comparabile a quella con password sbagliata
# (mitiga l'enumerazione utenti via timing).
_DUMMY_PASSWORD_HASH = hash_password(str(uuid.uuid4()))


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
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
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
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        user=MeResponse(
            **UserOut.model_validate(user).model_dump(),
            workspace_id=workspace.id,
            google_enabled=get_settings().google_enabled,
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))

    if user is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    token_response = await _build_token_response(db, user)
    refresh_token = await create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)
    return token_response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None),
) -> TokenResponse:
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
    _set_refresh_cookie(response, new_refresh_token)
    return token_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, refresh_token: str | None = Cookie(default=None)
) -> None:
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
    )

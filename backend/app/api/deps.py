import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.workspace_member import WorkspaceMember

bearer_scheme = HTTPBearer(auto_error=False)


async def set_rls_current_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Imposta app.current_user_id per la transazione corrente (SET LOCAL).

    Usata sia da `get_current_user` (dopo aver verificato il JWT) sia dal
    flow di registrazione (subito dopo aver creato la riga `users`, prima di
    inserire il workspace personale: senza questo, la WITH CHECK di RLS su
    `workspaces` rifiuterebbe l'insert perche' nessuna identita' e' ancora
    "attiva" sulla sessione). `set_config(..., true)` equivale a SET LOCAL ma,
    a differenza della sintassi SET diretta, accetta un bind parameter.
    """
    await db.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    await set_rls_current_user(db, user_id)

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    return user


async def get_primary_workspace_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    # In V1 ogni utente ha esattamente un workspace personale (creato alla
    # registrazione). Il modello dati supporta gia' piu' workspace per utente
    # in futuro; quando servira' selezionarne uno esplicitamente (family
    # workspace, SPEC §6), questo e' il punto da estendere. Richiede che
    # app.current_user_id sia gia' impostato sulla sessione (RLS).
    result = await db.execute(
        select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id)
    )
    return result.scalars().first()


async def get_current_workspace_id(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    workspace_id = await get_primary_workspace_id(db, user.id)
    if workspace_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No workspace found for user")
    return workspace_id

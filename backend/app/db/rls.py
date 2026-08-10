"""Meccanismo di identita' RLS condiviso tra le richieste HTTP (`app/api/deps.py`)
e il worker asincrono (`app/worker/jobs/`).

Entrambi devono impostare `app.current_user_id` sulla sessione DB prima di
qualunque query tenant-scoped, cosi' le policy di Row-Level Security (basate
su `is_workspace_member`, vedi migration 0002) si applicano davvero. Il
worker NON ha una richiesta HTTP ne' un JWT: usa lo stesso helper con
l'identita' dell'utente che ha creato l'import (`imports.created_by_user_id`)
— mai `SET ROLE lumio_rls_helper`/BYPASSRLS, l'isolamento a doppio livello
deve reggere anche li' (regola non negoziabile di CLAUDE.md).
"""
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory


async def set_rls_current_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Imposta app.current_user_id per la transazione corrente (SET LOCAL).

    `set_config(..., true)` equivale a SET LOCAL ma, a differenza della
    sintassi SET diretta, accetta un bind parameter. ATTENZIONE: vale solo
    per la transazione corrente — scade al commit. Una query RLS-dipendente
    eseguita dopo un `await db.commit()` nella stessa sessione gira senza
    identita' impostata e le policy negano tutto silenziosamente.
    """
    await db.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
    )


@asynccontextmanager
async def rls_session(user_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Apre una sessione DB con l'identita' RLS gia' impostata.

    Usata dal worker (nessuna richiesta HTTP/dependency injection disponibile)
    per ottenere una sessione che rispetta la RLS con la stessa identita' con
    cui l'utente ha creato l'import, invece di bypassarla.
    """
    async with async_session_factory() as session:
        await set_rls_current_user(session, user_id)
        yield session

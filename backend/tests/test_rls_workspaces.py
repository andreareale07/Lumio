"""Test di sicurezza a livello di database: bypassano completamente l'API e
il codice applicativo, parlando direttamente con Postgres con lo stesso
ruolo non-superuser che usa l'app (lumio_app). Provano che l'isolamento
multi-tenant tiene anche se il codice applicativo avesse un bug — e' la
Row-Level Security stessa a bloccare l'accesso cross-tenant, non un
controllo `if workspace.owner_id == current_user.id` nel codice Python.
"""
import uuid

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy import text

from app.db.base import async_session_factory


async def _set_current_user(session, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
    )


async def _create_user_with_workspace(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name) "
                "VALUES (:id, :email, 'x', 'Test')"
            ),
            {"id": str(user_id), "email": email},
        )
        await _set_current_user(session, user_id)
        workspace_id = (
            await session.execute(
                text(
                    "INSERT INTO workspaces (name, owner_user_id) "
                    "VALUES ('Personale', :owner) RETURNING id"
                ),
                {"owner": str(user_id)},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES (:w, :u, 'owner')"
            ),
            {"w": str(workspace_id), "u": str(user_id)},
        )
        await session.commit()
    return user_id, workspace_id


async def test_user_cannot_select_another_workspace_via_rls():
    user_a, workspace_a = await _create_user_with_workspace("rls-a@example.com")
    _, workspace_b = await _create_user_with_workspace("rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)

        direct_lookup = await session.execute(
            text("SELECT id FROM workspaces WHERE id = :wid"), {"wid": str(workspace_b)}
        )
        assert direct_lookup.first() is None

        all_visible = await session.execute(text("SELECT id FROM workspaces"))
        assert {row[0] for row in all_visible} == {workspace_a}


async def test_user_cannot_see_another_users_membership_row_via_rls():
    user_a, workspace_a = await _create_user_with_workspace("rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)

        all_visible = await session.execute(text("SELECT workspace_id, user_id FROM workspace_members"))
        rows = {(row[0], row[1]) for row in all_visible}
        assert rows == {(workspace_a, user_a)}


async def test_user_cannot_update_another_users_workspace_via_rls():
    # Sistema di valute (migration 0030): workspaces ora ha una policy
    # UPDATE, ristretta a is_workspace_owner — un utente senza alcuna
    # relazione con un workspace non deve poter cambiarne base_currency.
    user_a, workspace_a = await _create_user_with_workspace("rls-g@example.com")
    _, workspace_b = await _create_user_with_workspace("rls-h@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("UPDATE workspaces SET base_currency = 'USD' WHERE id = :id"),
            {"id": str(workspace_b)},
        )
        assert result.rowcount == 0
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        # L'owner PUO' invece aggiornare il proprio workspace.
        result = await session.execute(
            text("UPDATE workspaces SET base_currency = 'USD' WHERE id = :id"),
            {"id": str(workspace_a)},
        )
        assert result.rowcount == 1
        await session.commit()


async def test_user_cannot_join_another_users_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("rls-e@example.com")
    _, workspace_b = await _create_user_with_workspace("rls-f@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)

        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO workspace_members (workspace_id, user_id, role) "
                    "VALUES (:w, :u, 'owner')"
                ),
                {"w": str(workspace_b), "u": str(user_a)},
            )

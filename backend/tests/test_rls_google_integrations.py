"""Test di sicurezza a livello di database per `google_integrations`
(milestone 10) — stesso principio di `test_rls_market_data.py`: bypassano
completamente l'API e parlano direttamente con Postgres come lumio_app.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.base import async_session_factory


async def _set_current_user(session, user_id: uuid.UUID) -> None:
    await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)})


async def _create_user_with_workspace(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text("INSERT INTO users (id, email, password_hash, display_name) VALUES (:id, :email, 'x', 'Test')"),
            {"id": str(user_id), "email": email},
        )
        await _set_current_user(session, user_id)
        workspace_id = (
            await session.execute(
                text("INSERT INTO workspaces (name, owner_user_id) VALUES ('Personale', :owner) RETURNING id"),
                {"owner": str(user_id)},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (:w, :u, 'owner')"),
            {"w": str(workspace_id), "u": str(user_id)},
        )
        await session.commit()
    return user_id, workspace_id


_INSERT_INTEGRATION = (
    "INSERT INTO google_integrations "
    "(workspace_id, google_account_email, credentials_encrypted, spreadsheet_id, spreadsheet_url) "
    "VALUES (:w, :email, 'enc', :sheet_id, 'https://x')"
)


async def test_user_cannot_select_another_workspace_google_integration_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("goog-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("goog-rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        integration_id = (
            await session.execute(
                text(_INSERT_INTEGRATION + " RETURNING id"),
                {"w": str(workspace_b), "email": "b@example.com", "sheet_id": "sheet-b"},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM google_integrations WHERE id = :id"), {"id": str(integration_id)}
        )
        assert result.first() is None


async def test_user_cannot_insert_google_integration_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("goog-rls-c@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("goog-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(_INSERT_INTEGRATION),
                {"w": str(workspace_b), "email": "intruder@example.com", "sheet_id": "sheet-x"},
            )


async def test_at_most_one_google_integration_per_workspace():
    user_a, workspace_a = await _create_user_with_workspace("goog-rls-unique@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text(_INSERT_INTEGRATION), {"w": str(workspace_a), "email": "a@example.com", "sheet_id": "sheet-1"}
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(_INSERT_INTEGRATION), {"w": str(workspace_a), "email": "a2@example.com", "sheet_id": "sheet-2"}
            )

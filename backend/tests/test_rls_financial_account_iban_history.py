"""Test di sicurezza a livello di database per
financial_account_iban_history (milestone 09.5c) — stesso pattern di
test_rls_job_runs.py: bypassano completamente l'API.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

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


async def _create_account(session, workspace_id: uuid.UUID) -> uuid.UUID:
    return (
        await session.execute(
            text(
                "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                "VALUES (:w, 'Conto', 'checking', 'EUR') RETURNING id"
            ),
            {"w": str(workspace_id)},
        )
    ).scalar_one()


async def test_user_cannot_select_another_workspace_iban_history_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("iban-hist-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("iban-hist-rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        account_id = await _create_account(session, workspace_b)
        history_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_account_iban_history (workspace_id, financial_account_id, iban) "
                    "VALUES (:w, :a, 'DE44500105175407324931') RETURNING id"
                ),
                {"w": str(workspace_b), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM financial_account_iban_history WHERE id = :id"), {"id": str(history_id)}
        )
        assert result.first() is None


async def test_user_cannot_insert_iban_history_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("iban-hist-rls-c@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("iban-hist-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO financial_account_iban_history (workspace_id, financial_account_id, iban) "
                    "VALUES (:w, gen_random_uuid(), 'DE44500105175407324931')"
                ),
                {"w": str(workspace_b)},
            )


async def test_iban_history_unique_per_account_and_iban():
    user_a, workspace_a = await _create_user_with_workspace("iban-hist-rls-unique@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        account_id = await _create_account(session, workspace_a)
        await session.execute(
            text(
                "INSERT INTO financial_account_iban_history (workspace_id, financial_account_id, iban) "
                "VALUES (:w, :a, 'DE44500105175407324931')"
            ),
            {"w": str(workspace_a), "a": str(account_id)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO financial_account_iban_history (workspace_id, financial_account_id, iban) "
                    "VALUES (:w, :a, 'DE44500105175407324931')"
                ),
                {"w": str(workspace_a), "a": str(account_id)},
            )

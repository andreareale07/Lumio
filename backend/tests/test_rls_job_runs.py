"""Test di sicurezza a livello di database per job_runs (stato persistente
dei job async, gap UX emerso testando M09b) — stesso pattern di
test_rls_market_data.py: bypassano completamente l'API.
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


async def test_user_cannot_select_another_workspace_job_run_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("jr-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("jr-rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        run_id = (
            await session.execute(
                text(
                    "INSERT INTO job_runs (workspace_id, job_kind, status, started_at) "
                    "VALUES (:w, 'market_data_refresh', 'running', now()) RETURNING id"
                ),
                {"w": str(workspace_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(text("SELECT id FROM job_runs WHERE id = :id"), {"id": str(run_id)})
        assert result.first() is None


async def test_user_cannot_insert_job_run_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("jr-rls-c@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("jr-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO job_runs (workspace_id, job_kind, status, started_at) "
                    "VALUES (:w, 'market_data_refresh', 'running', now())"
                ),
                {"w": str(workspace_b)},
            )


async def test_job_runs_unique_per_workspace_and_job_kind():
    user_a, workspace_a = await _create_user_with_workspace("jr-rls-unique@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO job_runs (workspace_id, job_kind, status, started_at) "
                "VALUES (:w, 'market_data_refresh', 'running', now())"
            ),
            {"w": str(workspace_a)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO job_runs (workspace_id, job_kind, status, started_at) "
                    "VALUES (:w, 'market_data_refresh', 'running', now())"
                ),
                {"w": str(workspace_a)},
            )

"""Test di sicurezza a livello di database per `ai_profiles` (milestone 07)
— stesso principio di test_rls_rules_classifications.py: bypassano
completamente l'API e parlano direttamente con Postgres come lumio_app.
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


async def test_user_cannot_select_another_workspace_ai_profile_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("ai-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("ai-rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        profile_b = (
            await session.execute(
                text(
                    "INSERT INTO ai_profiles (workspace_id, name, provider) "
                    "VALUES (:w, 'Profilo B', 'ollama') RETURNING id"
                ),
                {"w": str(workspace_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        direct_lookup = await session.execute(
            text("SELECT id FROM ai_profiles WHERE id = :pid"), {"pid": str(profile_b)}
        )
        assert direct_lookup.first() is None


async def test_user_cannot_insert_ai_profile_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("ai-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("ai-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO ai_profiles (workspace_id, name, provider) "
                    "VALUES (:w, 'Intrusa', 'ollama')"
                ),
                {"w": str(workspace_b)},
            )


async def test_at_most_one_active_profile_per_workspace():
    user_a, workspace_a = await _create_user_with_workspace("ai-rls-active@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO ai_profiles (workspace_id, name, provider, is_active) "
                "VALUES (:w, 'Prima', 'ollama', true)"
            ),
            {"w": str(workspace_a)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO ai_profiles (workspace_id, name, provider, is_active) "
                    "VALUES (:w, 'Seconda', 'ollama', true)"
                ),
                {"w": str(workspace_a)},
            )

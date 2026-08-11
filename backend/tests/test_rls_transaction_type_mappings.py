"""Test di sicurezza a livello di database per transaction_type_mappings
(milestone 09.5) — stesso pattern di test_rls_job_runs.py: bypassano
completamente l'API.
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


async def test_user_cannot_select_another_workspace_type_mapping_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("ttm-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("ttm-rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        mapping_id = (
            await session.execute(
                text(
                    "INSERT INTO transaction_type_mappings "
                    "(workspace_id, parser_type, source_type_raw, transaction_type) "
                    "VALUES (:w, 'trade_republic_pdf', 'Bonifico', 'transfer') RETURNING id"
                ),
                {"w": str(workspace_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM transaction_type_mappings WHERE id = :id"), {"id": str(mapping_id)}
        )
        assert result.first() is None


async def test_user_cannot_insert_type_mapping_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("ttm-rls-c@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("ttm-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO transaction_type_mappings "
                    "(workspace_id, parser_type, source_type_raw, transaction_type) "
                    "VALUES (:w, 'trade_republic_pdf', 'Bonifico', 'transfer')"
                ),
                {"w": str(workspace_b)},
            )


async def test_type_mappings_unique_per_workspace_parser_and_label():
    user_a, workspace_a = await _create_user_with_workspace("ttm-rls-unique@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO transaction_type_mappings "
                "(workspace_id, parser_type, source_type_raw, transaction_type) "
                "VALUES (:w, 'trade_republic_pdf', 'Bonifico', 'transfer')"
            ),
            {"w": str(workspace_a)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO transaction_type_mappings "
                    "(workspace_id, parser_type, source_type_raw, transaction_type) "
                    "VALUES (:w, 'trade_republic_pdf', 'Bonifico', 'fee')"
                ),
                {"w": str(workspace_a)},
            )


async def test_type_mappings_rejects_unknown_transaction_type():
    user_a, workspace_a = await _create_user_with_workspace("ttm-rls-badtype@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="check"):
            await session.execute(
                text(
                    "INSERT INTO transaction_type_mappings "
                    "(workspace_id, parser_type, source_type_raw, transaction_type) "
                    "VALUES (:w, 'trade_republic_pdf', 'Bonifico', 'not_a_real_type')"
                ),
                {"w": str(workspace_a)},
            )

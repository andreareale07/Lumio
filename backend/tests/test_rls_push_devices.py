"""RLS di `push_devices`: owner-only, anche tra membri dello STESSO workspace.

Le righe sono reali: con zero righe che matchano Postgres non invoca la policy.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.base import async_session_factory
from tests.test_rls_open_banking import _create_shared_workspace, _create_user, _set_user


async def _fixture(suffix: str):
    owner = await _create_user(f"push-owner-{suffix}@example.com")
    other = await _create_user(f"push-other-{suffix}@example.com")
    workspace_id = await _create_shared_workspace(owner, other)
    async with async_session_factory() as session:
        await _set_user(session, owner)
        device_id = (
            await session.execute(
                text(
                    "INSERT INTO push_devices (workspace_id, owner_user_id, platform, token) "
                    "VALUES (:w, :o, 'android', :t) RETURNING id"
                ),
                {"w": str(workspace_id), "o": str(owner), "t": "tok-" + uuid.uuid4().hex},
            )
        ).scalar_one()
        await session.commit()
    return owner, other, workspace_id, device_id


async def test_owner_sees_own_device():
    owner, _other, _ws, device_id = await _fixture("sel-own")
    async with async_session_factory() as session:
        await _set_user(session, owner)
        rows = await session.execute(text("SELECT id FROM push_devices WHERE id = :i"), {"i": str(device_id)})
        assert rows.first() is not None


async def test_other_member_cannot_select_update_or_delete():
    _owner, other, _ws, device_id = await _fixture("other")
    async with async_session_factory() as session:
        await _set_user(session, other)
        assert (await session.execute(text("SELECT id FROM push_devices WHERE id = :i"), {"i": str(device_id)})).first() is None
        updated = await session.execute(text("UPDATE push_devices SET platform = 'ios' WHERE id = :i"), {"i": str(device_id)})
        assert updated.rowcount == 0
        deleted = await session.execute(text("DELETE FROM push_devices WHERE id = :i"), {"i": str(device_id)})
        assert deleted.rowcount == 0


async def test_other_member_cannot_insert_for_someone_else():
    owner, other, workspace_id, _device_id = await _fixture("ins")
    async with async_session_factory() as session:
        await _set_user(session, other)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO push_devices (workspace_id, owner_user_id, platform, token) "
                    "VALUES (:w, :o, 'android', 'tok-forged')"
                ),
                {"w": str(workspace_id), "o": str(owner)},
            )

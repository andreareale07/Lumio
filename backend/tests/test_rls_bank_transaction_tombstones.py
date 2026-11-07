"""RLS di `bank_transaction_tombstones` (workspace-scoped, 4 policy separate).

Ogni test crea una riga reale: con zero righe Postgres non invoca la policy e il
test sarebbe verde a vuoto (vedi `progetto-database-rls.md`).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.base import async_session_factory
from tests.test_rls_open_banking import _create_shared_workspace, _create_user, _set_user


async def _seed(suffix: str):
    owner = await _create_user(f"ts-owner-{suffix}@example.com")
    outsider = await _create_user(f"ts-out-{suffix}@example.com")
    member = await _create_user(f"ts-member-{suffix}@example.com")
    workspace_id = await _create_shared_workspace(owner, member)
    async with async_session_factory() as session:
        await _set_user(session, owner)
        account_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                    "VALUES (:w, 'Conto', 'checking', 'EUR') RETURNING id"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()
        tombstone_id = (
            await session.execute(
                text(
                    "INSERT INTO bank_transaction_tombstones (workspace_id, financial_account_id, external_id) "
                    "VALUES (:w, :a, 'ext-1') RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()
    return owner, member, outsider, workspace_id, account_id, tombstone_id


async def test_workspace_members_can_read_the_tombstone():
    owner, member, _out, _ws, _acc, tombstone_id = await _seed("sel-ok")
    for user in (owner, member):
        async with async_session_factory() as session:
            await _set_user(session, user)
            row = await session.execute(
                text("SELECT id FROM bank_transaction_tombstones WHERE id = :i"), {"i": str(tombstone_id)}
            )
            assert row.first() is not None


async def test_outsider_cannot_select():
    _owner, _member, outsider, _ws, _acc, tombstone_id = await _seed("sel-out")
    async with async_session_factory() as session:
        await _set_user(session, outsider)
        rows = await session.execute(
            text("SELECT id FROM bank_transaction_tombstones WHERE id = :i"), {"i": str(tombstone_id)}
        )
        assert rows.first() is None


async def test_outsider_cannot_insert():
    _owner, _member, outsider, ws, acc, _t = await _seed("ins-out")
    async with async_session_factory() as session:
        await _set_user(session, outsider)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO bank_transaction_tombstones (workspace_id, financial_account_id, external_id) "
                    "VALUES (:w, :a, 'ext-2')"
                ),
                {"w": str(ws), "a": str(acc)},
            )


async def test_outsider_cannot_update():
    _owner, _member, outsider, _ws, _acc, tombstone_id = await _seed("upd-out")
    async with async_session_factory() as session:
        await _set_user(session, outsider)
        result = await session.execute(
            text("UPDATE bank_transaction_tombstones SET external_id = 'x' WHERE id = :i"), {"i": str(tombstone_id)}
        )
        assert result.rowcount == 0


async def test_outsider_cannot_delete_but_member_can():
    _owner, member, outsider, _ws, _acc, tombstone_id = await _seed("del")
    async with async_session_factory() as session:
        await _set_user(session, outsider)
        result = await session.execute(
            text("DELETE FROM bank_transaction_tombstones WHERE id = :i"), {"i": str(tombstone_id)}
        )
        assert result.rowcount == 0
    async with async_session_factory() as session:
        await _set_user(session, member)
        result = await session.execute(
            text("DELETE FROM bank_transaction_tombstones WHERE id = :i"), {"i": str(tombstone_id)}
        )
        assert result.rowcount == 1


async def test_one_tombstone_per_account_and_external_id():
    owner, _member, _out, ws, acc, _t = await _seed("unique")
    async with async_session_factory() as session:
        await _set_user(session, owner)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO bank_transaction_tombstones (workspace_id, financial_account_id, external_id) "
                    "VALUES (:w, :a, 'ext-1')"
                ),
                {"w": str(ws), "a": str(acc)},
            )


async def test_deleting_the_account_removes_its_tombstones():
    owner, _member, _out, ws, acc, tombstone_id = await _seed("cascade")
    async with async_session_factory() as session:
        await _set_user(session, owner)
        await session.execute(
            text("DELETE FROM financial_accounts WHERE id = :a AND workspace_id = :w"), {"a": str(acc), "w": str(ws)}
        )
        left = await session.execute(
            text("SELECT 1 FROM bank_transaction_tombstones WHERE id = :i"), {"i": str(tombstone_id)}
        )
        assert left.first() is None

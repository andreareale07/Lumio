"""Ricalcolo una tantum di tutte le posizioni (`scripts/recompute_positions.py`):
ripara i valori salvati su `positions` dopo una correzione al calcolo, con
l'identita' RLS del proprietario e un dry-run che non scrive nulla."""
import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.services.position_service import recompute_all_positions
from tests.test_portfolio_api import (
    _create_account,
    _create_asset,
    _create_investment_transaction,
    _register,
)

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recompute_positions.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("recompute_positions_script", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _owner(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with async_session_factory() as session:
        user_id = (await session.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})).scalar_one()
    async with rls_session(user_id) as db:
        workspace_id = (await db.execute(text("SELECT id FROM workspaces WHERE owner_user_id = :u"), {"u": user_id})).scalar_one()
    return user_id, workspace_id


async def _corrupt_realized(user_id: uuid.UUID, value: str) -> None:
    async with rls_session(user_id) as db:
        await db.execute(text("UPDATE positions SET realized_pl = :v"), {"v": value})
        await db.commit()


async def _stored_realized(user_id: uuid.UUID) -> Decimal:
    async with rls_session(user_id) as db:
        return (await db.execute(text("SELECT realized_pl FROM positions"))).scalar_one()


async def _setup(client, email: str) -> tuple[uuid.UUID, uuid.UUID]:
    token = await _register(client, email)
    account_id = await _create_account(client, token)
    asset_id = await _create_asset(client, token)
    await _create_investment_transaction(client, token, account_id, asset_id=asset_id, quantity="10", price="100")
    sell = await _create_investment_transaction(
        client, token, account_id, asset_id=asset_id, trade_date="2026-02-01", type="sell",
        quantity="10", price="110", amount="1100.00",
    )
    assert sell.status_code == 201, sell.text
    return await _owner(email)


async def test_recompute_all_positions_repairs_a_stale_stored_value(client):
    user_id, workspace_id = await _setup(client, "recompute-repair@example.com")
    assert await _stored_realized(user_id) == Decimal("100.00")
    await _corrupt_realized(user_id, "999999.99")

    async with rls_session(user_id) as db:
        report = await recompute_all_positions(db, workspace_id)
        await db.commit()

    changes = report.changes
    assert report.checked == 1
    assert len(changes) == 1
    assert changes[0].old_realized_pl == Decimal("999999.99")
    assert changes[0].new_realized_pl == Decimal("100.00")
    assert await _stored_realized(user_id) == Decimal("100.00")

    async with rls_session(user_id) as db:
        assert (await recompute_all_positions(db, workspace_id)).changes == []


async def test_script_dry_run_writes_nothing_and_real_run_repairs(client):
    user_id, workspace_id = await _setup(client, "recompute-script@example.com")
    await _corrupt_realized(user_id, "999.00")
    script = _load_script()

    assert await script._recompute_workspace(workspace_id, user_id, dry_run=True) == 1
    assert await _stored_realized(user_id) == Decimal("999.00")

    assert await script._recompute_workspace(workspace_id, user_id, dry_run=False) == 1
    assert await _stored_realized(user_id) == Decimal("100.00")


async def test_recompute_is_scoped_to_the_workspace_of_the_user(client):
    owner_id, owner_workspace = await _setup(client, "recompute-owner@example.com")
    other_id, other_workspace = await _setup(client, "recompute-other@example.com")
    await _corrupt_realized(other_id, "555.00")

    async with rls_session(owner_id) as db:
        assert (await recompute_all_positions(db, owner_workspace)).changes == []
        await db.commit()

    assert await _stored_realized(other_id) == Decimal("555.00")
    assert other_workspace != owner_workspace

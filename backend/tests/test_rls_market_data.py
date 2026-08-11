"""Test di sicurezza a livello di database per il dominio Market Data
(milestone 09b) — stesso principio di `test_rls_portfolio.py`: bypassano
completamente l'API e parlano direttamente con Postgres come lumio_app.
Copre le 4 tabelle nuove: market_data_profiles, asset_prices,
portfolio_snapshots, net_worth_snapshots.
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


async def _create_asset(session, workspace_id: uuid.UUID) -> uuid.UUID:
    return (
        await session.execute(
            text(
                "INSERT INTO assets (workspace_id, name, asset_type, currency) "
                "VALUES (:w, 'VWCE', 'etf', 'EUR') RETURNING id"
            ),
            {"w": str(workspace_id)},
        )
    ).scalar_one()


async def test_user_cannot_select_another_workspace_market_data_profile_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("md-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("md-rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        profile_id = (
            await session.execute(
                text(
                    "INSERT INTO market_data_profiles (workspace_id, name, provider) "
                    "VALUES (:w, 'Manuale', 'manual') RETURNING id"
                ),
                {"w": str(workspace_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM market_data_profiles WHERE id = :id"), {"id": str(profile_id)}
        )
        assert result.first() is None


async def test_user_cannot_insert_market_data_profile_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("md-rls-c@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("md-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO market_data_profiles (workspace_id, name, provider) "
                    "VALUES (:w, 'Intrusa', 'manual')"
                ),
                {"w": str(workspace_b)},
            )


async def test_at_most_one_active_market_data_profile_per_workspace():
    user_a, workspace_a = await _create_user_with_workspace("md-rls-active@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO market_data_profiles (workspace_id, name, provider, is_active) "
                "VALUES (:w, 'Prima', 'manual', true)"
            ),
            {"w": str(workspace_a)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO market_data_profiles (workspace_id, name, provider, is_active) "
                    "VALUES (:w, 'Seconda', 'stooq', true)"
                ),
                {"w": str(workspace_a)},
            )


async def test_user_cannot_select_another_workspace_asset_price_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("md-rls-price-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("md-rls-price-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        asset_id = await _create_asset(session, workspace_b)
        price_id = (
            await session.execute(
                text(
                    "INSERT INTO asset_prices (workspace_id, asset_id, price_date, price, currency, source) "
                    "VALUES (:w, :a, '2026-08-01', 100.00, 'EUR', 'manual') RETURNING id"
                ),
                {"w": str(workspace_b), "a": str(asset_id)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM asset_prices WHERE id = :id"), {"id": str(price_id)}
        )
        assert result.first() is None


async def test_one_asset_price_per_day_enforced_at_db_level():
    user_a, workspace_a = await _create_user_with_workspace("md-rls-oneprice@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        asset_id = await _create_asset(session, workspace_a)
        await session.execute(
            text(
                "INSERT INTO asset_prices (workspace_id, asset_id, price_date, price, currency, source) "
                "VALUES (:w, :a, '2026-08-01', 100.00, 'EUR', 'manual')"
            ),
            {"w": str(workspace_a), "a": str(asset_id)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO asset_prices (workspace_id, asset_id, price_date, price, currency, source) "
                    "VALUES (:w, :a, '2026-08-01', 105.00, 'EUR', 'stooq')"
                ),
                {"w": str(workspace_a), "a": str(asset_id)},
            )


async def test_user_cannot_select_another_workspace_net_worth_snapshot_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("md-rls-nw-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("md-rls-nw-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        snapshot_id = (
            await session.execute(
                text(
                    "INSERT INTO net_worth_snapshots "
                    "(workspace_id, snapshot_date, currency, liquidity, debt, investments, net_worth) "
                    "VALUES (:w, '2026-08-01', 'EUR', 1000, 0, 0, 1000) RETURNING id"
                ),
                {"w": str(workspace_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM net_worth_snapshots WHERE id = :id"), {"id": str(snapshot_id)}
        )
        assert result.first() is None


async def test_portfolio_snapshots_allow_one_aggregate_row_per_day_and_reject_duplicate():
    """`portfolio_id IS NULL` rappresenta l'aggregato "tutti i conti" — deve
    restare unico per giorno esattamente come una riga con portfolio
    specifico (vedi indici parziali dedicati in 0010_market_data.py)."""
    user_a, workspace_a = await _create_user_with_workspace("md-rls-ps@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO portfolio_snapshots "
                "(workspace_id, portfolio_id, snapshot_date, currency, market_value, cost_basis, unrealized_pl, realized_pl) "
                "VALUES (:w, NULL, '2026-08-01', 'EUR', 1000, 1000, 0, 0)"
            ),
            {"w": str(workspace_a)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            await session.execute(
                text(
                    "INSERT INTO portfolio_snapshots "
                    "(workspace_id, portfolio_id, snapshot_date, currency, market_value, cost_basis, unrealized_pl, realized_pl) "
                    "VALUES (:w, NULL, '2026-08-01', 'EUR', 1100, 1000, 100, 0)"
                ),
                {"w": str(workspace_a)},
            )

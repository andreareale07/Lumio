"""Test di sicurezza a livello di database per il dominio Portfolio
(milestone 09) — stesso principio di `test_rls_ai_settings.py`: bypassano
completamente l'API e parlano direttamente con Postgres come lumio_app.
Copre le 5 tabelle nuove: assets, portfolios, portfolio_accounts,
investment_transactions, positions.
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
                "VALUES (:w, 'Conto', 'brokerage', 'EUR') RETURNING id"
            ),
            {"w": str(workspace_id)},
        )
    ).scalar_one()


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


async def _create_portfolio(session, workspace_id: uuid.UUID) -> uuid.UUID:
    return (
        await session.execute(
            text(
                "INSERT INTO portfolios (workspace_id, name, currency) "
                "VALUES (:w, 'Investimenti', 'EUR') RETURNING id"
            ),
            {"w": str(workspace_id)},
        )
    ).scalar_one()


@pytest.mark.parametrize(
    "table, insert_sql",
    [
        (
            "assets",
            "INSERT INTO assets (workspace_id, name, asset_type, currency) "
            "VALUES (:w, 'Intrusa', 'etf', 'EUR')",
        ),
        (
            "portfolios",
            "INSERT INTO portfolios (workspace_id, name, currency) VALUES (:w, 'Intrusa', 'EUR')",
        ),
    ],
)
async def test_user_cannot_insert_into_another_workspace(table, insert_sql):
    user_a, _workspace_a = await _create_user_with_workspace(f"pf-rls-a-{table}@example.com")
    _user_b, workspace_b = await _create_user_with_workspace(f"pf-rls-b-{table}@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(text(insert_sql), {"w": str(workspace_b)})


async def test_user_cannot_select_another_workspace_asset_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("pf-rls-asset-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("pf-rls-asset-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        asset_id = await _create_asset(session, workspace_b)
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(text("SELECT id FROM assets WHERE id = :id"), {"id": str(asset_id)})
        assert result.first() is None


async def test_user_cannot_select_another_workspace_portfolio_via_rls():
    """Gap chiuso in milestone 11 (SPEC §56): `portfolios` aveva gia' un test
    di INSERT cross-tenant (parametrizzato sopra) ma nessuno di SELECT, a
    differenza di assets/investment_transactions/positions/portfolio_accounts
    sotto in questo stesso file."""
    user_a, _workspace_a = await _create_user_with_workspace("pf-rls-portfolio-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("pf-rls-portfolio-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        portfolio_id = await _create_portfolio(session, workspace_b)
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM portfolios WHERE id = :id"), {"id": str(portfolio_id)}
        )
        assert result.first() is None


async def test_user_cannot_select_another_workspace_investment_transaction_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("pf-rls-itx-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("pf-rls-itx-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        account_id = await _create_account(session, workspace_b)
        asset_id = await _create_asset(session, workspace_b)
        txn_id = (
            await session.execute(
                text(
                    "INSERT INTO investment_transactions "
                    "(workspace_id, financial_account_id, asset_id, trade_date, type, quantity, price, amount, currency) "
                    "VALUES (:w, :a, :s, '2026-01-01', 'buy', 10, 100, -1000, 'EUR') RETURNING id"
                ),
                {"w": str(workspace_b), "a": str(account_id), "s": str(asset_id)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM investment_transactions WHERE id = :id"), {"id": str(txn_id)}
        )
        assert result.first() is None


async def test_user_cannot_insert_investment_transaction_referencing_another_workspace_account():
    """Non solo la RLS: la FK composita (workspace_id, financial_account_id)
    deve rifiutare anche un tentativo che passasse la RLS con un workspace_id
    proprio ma un conto id di un altro workspace (SPEC §57)."""
    user_a, workspace_a = await _create_user_with_workspace("pf-rls-fk-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("pf-rls-fk-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        account_b = await _create_account(session, workspace_b)
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        asset_a = await _create_asset(session, workspace_a)
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO investment_transactions "
                    "(workspace_id, financial_account_id, asset_id, trade_date, type, quantity, price, amount, currency) "
                    "VALUES (:w, :a, :s, '2026-01-01', 'buy', 10, 100, -1000, 'EUR')"
                ),
                {"w": str(workspace_a), "a": str(account_b), "s": str(asset_a)},
            )


async def test_user_cannot_select_another_workspace_position_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("pf-rls-pos-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("pf-rls-pos-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        account_id = await _create_account(session, workspace_b)
        asset_id = await _create_asset(session, workspace_b)
        position_id = (
            await session.execute(
                text(
                    "INSERT INTO positions (workspace_id, financial_account_id, asset_id, quantity, average_cost, currency) "
                    "VALUES (:w, :a, :s, 10, 100, 'EUR') RETURNING id"
                ),
                {"w": str(workspace_b), "a": str(account_id), "s": str(asset_id)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM positions WHERE id = :id"), {"id": str(position_id)}
        )
        assert result.first() is None


async def test_user_cannot_select_another_workspace_portfolio_account_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("pf-rls-pa-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("pf-rls-pa-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        account_id = await _create_account(session, workspace_b)
        portfolio_id = await _create_portfolio(session, workspace_b)
        link_id = (
            await session.execute(
                text(
                    "INSERT INTO portfolio_accounts (workspace_id, portfolio_id, financial_account_id) "
                    "VALUES (:w, :p, :a) RETURNING id"
                ),
                {"w": str(workspace_b), "p": str(portfolio_id), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM portfolio_accounts WHERE id = :id"), {"id": str(link_id)}
        )
        assert result.first() is None


async def test_asset_isin_unique_per_workspace_case_insensitive_symbol():
    user_a, workspace_a = await _create_user_with_workspace("pf-rls-uniq@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text(
                "INSERT INTO assets (workspace_id, name, asset_type, currency, symbol) "
                "VALUES (:w, 'VWCE', 'etf', 'EUR', 'VWCE')"
            ),
            {"w": str(workspace_a)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="unique"):
            # Case-insensitive: "vwce" deve collidere con "VWCE" gia' salvato.
            await session.execute(
                text(
                    "INSERT INTO assets (workspace_id, name, asset_type, currency, symbol) "
                    "VALUES (:w, 'VWCE duplicato', 'etf', 'EUR', 'vwce')"
                ),
                {"w": str(workspace_a)},
            )

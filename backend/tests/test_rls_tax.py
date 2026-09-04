"""Test di sicurezza a livello di database per le 4 tabelle fiscali
(SPEC_TAX_REGIME.md FETTA 1) — stesso principio di test_rls_transaction_dedup.py:
bypassano l'API e parlano direttamente con Postgres come lumio_app, provando
che l'isolamento tiene anche con un bug applicativo. Tutti e 4 i comandi
(select/insert/update/delete), non solo select+insert."""
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


async def _create_account(user_id: uuid.UUID, workspace_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        account_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                    "VALUES (:w, 'Conto', 'brokerage', 'EUR') RETURNING id"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()
        await session.commit()
    return account_id


async def _create_asset(user_id: uuid.UUID, workspace_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        asset_id = (
            await session.execute(
                text(
                    "INSERT INTO assets (workspace_id, name, asset_type, currency) "
                    "VALUES (:w, 'Azione Test', 'stock', 'EUR') RETURNING id"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()
        await session.commit()
    return asset_id


async def _create_residence(user_id: uuid.UUID, workspace_id: uuid.UUID, year: int = 2024) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        row_id = (
            await session.execute(
                text(
                    "INSERT INTO workspace_tax_residences (workspace_id, fiscal_year, jurisdiction_code) "
                    "VALUES (:w, :y, 'IT') RETURNING id"
                ),
                {"w": str(workspace_id), "y": year},
            )
        ).scalar_one()
        await session.commit()
    return row_id


async def _create_regime(
    user_id: uuid.UUID, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        row_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_account_tax_regimes "
                    "(workspace_id, financial_account_id, regime_code, effective_from) "
                    "VALUES (:w, :a, 'amministrato', '2020-01-01') RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()
    return row_id


async def _create_classification(
    user_id: uuid.UUID, workspace_id: uuid.UUID, asset_id: uuid.UUID
) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        row_id = (
            await session.execute(
                text(
                    "INSERT INTO asset_tax_classifications (workspace_id, asset_id, jurisdiction_code, asset_class) "
                    "VALUES (:w, :a, 'IT', 'azioni') RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(asset_id)},
            )
        ).scalar_one()
        await session.commit()
    return row_id


async def _create_opening(
    user_id: uuid.UUID, workspace_id: uuid.UUID, account_id: uuid.UUID | None
) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        row_id = (
            await session.execute(
                text(
                    "INSERT INTO tax_loss_opening_balances "
                    "(workspace_id, financial_account_id, formation_date, formed_under_ruleset_code, "
                    " income_category, amount) "
                    "VALUES (:w, :a, '2020-01-01', 'IT-2014-07', 'redditi_diversi', 1000.00) RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id) if account_id else None},
            )
        ).scalar_one()
        await session.commit()
    return row_id


# --- workspace_tax_residences -------------------------------------------------


async def test_user_cannot_select_another_workspace_residence():
    user_a, _ = await _create_user_with_workspace("res-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("res-rls-b@example.com")
    residence_b = await _create_residence(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM workspace_tax_residences WHERE id = :i"), {"i": str(residence_b)}
        )
        assert result.first() is None


async def test_user_cannot_insert_residence_into_another_workspace():
    user_a, workspace_a = await _create_user_with_workspace("res-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("res-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO workspace_tax_residences (workspace_id, fiscal_year, jurisdiction_code) "
                    "VALUES (:w, 2024, 'IT')"
                ),
                {"w": str(workspace_b)},
            )


async def test_user_cannot_update_another_workspace_residence():
    user_a, _ = await _create_user_with_workspace("res-rls-e@example.com")
    user_b, workspace_b = await _create_user_with_workspace("res-rls-f@example.com")
    residence_b = await _create_residence(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text("UPDATE workspace_tax_residences SET jurisdiction_code = 'IT' WHERE id = :i"),
            {"i": str(residence_b)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT jurisdiction_code FROM workspace_tax_residences WHERE id = :i"), {"i": str(residence_b)}
        )
        assert result.scalar_one() == "IT"


async def test_user_cannot_delete_another_workspace_residence():
    user_a, _ = await _create_user_with_workspace("res-rls-g@example.com")
    user_b, workspace_b = await _create_user_with_workspace("res-rls-h@example.com")
    residence_b = await _create_residence(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(text("DELETE FROM workspace_tax_residences WHERE id = :i"), {"i": str(residence_b)})
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT id FROM workspace_tax_residences WHERE id = :i"), {"i": str(residence_b)}
        )
        assert result.first() is not None


# --- financial_account_tax_regimes ---------------------------------------------


async def test_user_cannot_select_another_workspace_regime():
    user_a, _ = await _create_user_with_workspace("reg-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("reg-rls-b@example.com")
    account_b = await _create_account(user_b, workspace_b)
    regime_b = await _create_regime(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM financial_account_tax_regimes WHERE id = :i"), {"i": str(regime_b)}
        )
        assert result.first() is None


async def test_user_cannot_insert_regime_into_another_workspace():
    user_a, workspace_a = await _create_user_with_workspace("reg-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("reg-rls-d@example.com")
    account_b = await _create_account(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO financial_account_tax_regimes "
                    "(workspace_id, financial_account_id, regime_code, effective_from) "
                    "VALUES (:w, :a, 'amministrato', '2020-01-01')"
                ),
                {"w": str(workspace_a), "a": str(account_b)},
            )


async def test_user_cannot_update_another_workspace_regime():
    user_a, _ = await _create_user_with_workspace("reg-rls-e@example.com")
    user_b, workspace_b = await _create_user_with_workspace("reg-rls-f@example.com")
    account_b = await _create_account(user_b, workspace_b)
    regime_b = await _create_regime(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text("UPDATE financial_account_tax_regimes SET regime_code = 'dichiarativo' WHERE id = :i"),
            {"i": str(regime_b)},
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT regime_code FROM financial_account_tax_regimes WHERE id = :i"), {"i": str(regime_b)}
        )
        assert result.scalar_one() == "amministrato"


async def test_user_cannot_delete_another_workspace_regime():
    user_a, _ = await _create_user_with_workspace("reg-rls-g@example.com")
    user_b, workspace_b = await _create_user_with_workspace("reg-rls-h@example.com")
    account_b = await _create_account(user_b, workspace_b)
    regime_b = await _create_regime(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(text("DELETE FROM financial_account_tax_regimes WHERE id = :i"), {"i": str(regime_b)})
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT id FROM financial_account_tax_regimes WHERE id = :i"), {"i": str(regime_b)}
        )
        assert result.first() is not None


async def test_regime_period_unique_constraint_blocks_duplicate_effective_from():
    user_id, workspace_id = await _create_user_with_workspace("reg-unique-a@example.com")
    account_id = await _create_account(user_id, workspace_id)
    await _create_regime(user_id, workspace_id, account_id)

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO financial_account_tax_regimes "
                    "(workspace_id, financial_account_id, regime_code, effective_from) "
                    "VALUES (:w, :a, 'dichiarativo', '2020-01-01')"
                ),
                {"w": str(workspace_id), "a": str(account_id)},
            )


# --- asset_tax_classifications --------------------------------------------------


async def test_user_cannot_select_another_workspace_classification():
    user_a, _ = await _create_user_with_workspace("cls-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("cls-rls-b@example.com")
    asset_b = await _create_asset(user_b, workspace_b)
    cls_b = await _create_classification(user_b, workspace_b, asset_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM asset_tax_classifications WHERE id = :i"), {"i": str(cls_b)}
        )
        assert result.first() is None


async def test_user_cannot_insert_classification_into_another_workspace():
    user_a, workspace_a = await _create_user_with_workspace("cls-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("cls-rls-d@example.com")
    asset_b = await _create_asset(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO asset_tax_classifications (workspace_id, asset_id, jurisdiction_code, asset_class) "
                    "VALUES (:w, :a, 'IT', 'azioni')"
                ),
                {"w": str(workspace_a), "a": str(asset_b)},
            )


async def test_user_cannot_update_another_workspace_classification():
    user_a, _ = await _create_user_with_workspace("cls-rls-e@example.com")
    user_b, workspace_b = await _create_user_with_workspace("cls-rls-f@example.com")
    asset_b = await _create_asset(user_b, workspace_b)
    cls_b = await _create_classification(user_b, workspace_b, asset_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text("UPDATE asset_tax_classifications SET asset_class = 'cripto' WHERE id = :i"), {"i": str(cls_b)}
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT asset_class FROM asset_tax_classifications WHERE id = :i"), {"i": str(cls_b)}
        )
        assert result.scalar_one() == "azioni"


async def test_user_cannot_delete_another_workspace_classification():
    user_a, _ = await _create_user_with_workspace("cls-rls-g@example.com")
    user_b, workspace_b = await _create_user_with_workspace("cls-rls-h@example.com")
    asset_b = await _create_asset(user_b, workspace_b)
    cls_b = await _create_classification(user_b, workspace_b, asset_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(text("DELETE FROM asset_tax_classifications WHERE id = :i"), {"i": str(cls_b)})
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT id FROM asset_tax_classifications WHERE id = :i"), {"i": str(cls_b)}
        )
        assert result.first() is not None


# --- tax_loss_opening_balances ------------------------------------------------


async def test_user_cannot_select_another_workspace_opening():
    user_a, _ = await _create_user_with_workspace("open-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("open-rls-b@example.com")
    opening_b = await _create_opening(user_b, workspace_b, None)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM tax_loss_opening_balances WHERE id = :i"), {"i": str(opening_b)}
        )
        assert result.first() is None


async def test_user_cannot_insert_opening_into_another_workspace():
    user_a, _ = await _create_user_with_workspace("open-rls-c@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("open-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO tax_loss_opening_balances "
                    "(workspace_id, financial_account_id, formation_date, formed_under_ruleset_code, "
                    " income_category, amount) "
                    "VALUES (:w, NULL, '2020-01-01', 'IT-2014-07', 'redditi_diversi', 1000.00)"
                ),
                {"w": str(workspace_b)},
            )


async def test_user_cannot_update_another_workspace_opening():
    user_a, _ = await _create_user_with_workspace("open-rls-e@example.com")
    user_b, workspace_b = await _create_user_with_workspace("open-rls-f@example.com")
    opening_b = await _create_opening(user_b, workspace_b, None)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text("UPDATE tax_loss_opening_balances SET amount = 1.00 WHERE id = :i"), {"i": str(opening_b)}
        )
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT amount FROM tax_loss_opening_balances WHERE id = :i"), {"i": str(opening_b)}
        )
        assert result.scalar_one() == 1000.00


async def test_user_cannot_delete_another_workspace_opening():
    user_a, _ = await _create_user_with_workspace("open-rls-g@example.com")
    user_b, workspace_b = await _create_user_with_workspace("open-rls-h@example.com")
    opening_b = await _create_opening(user_b, workspace_b, None)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(text("DELETE FROM tax_loss_opening_balances WHERE id = :i"), {"i": str(opening_b)})
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        result = await session.execute(
            text("SELECT id FROM tax_loss_opening_balances WHERE id = :i"), {"i": str(opening_b)}
        )
        assert result.first() is not None


async def test_opening_aggregate_perimeter_unique_constraint_blocks_duplicate_formation_date():
    user_id, workspace_id = await _create_user_with_workspace("open-unique-a@example.com")
    await _create_opening(user_id, workspace_id, None)

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO tax_loss_opening_balances "
                    "(workspace_id, financial_account_id, formation_date, formed_under_ruleset_code, "
                    " income_category, amount) "
                    "VALUES (:w, NULL, '2020-01-01', 'IT-2014-07', 'redditi_diversi', 500.00)"
                ),
                {"w": str(workspace_id)},
            )


async def test_opening_per_account_perimeter_unique_constraint_blocks_duplicate_formation_date():
    user_id, workspace_id = await _create_user_with_workspace("open-unique-b@example.com")
    account_id = await _create_account(user_id, workspace_id)
    await _create_opening(user_id, workspace_id, account_id)

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO tax_loss_opening_balances "
                    "(workspace_id, financial_account_id, formation_date, formed_under_ruleset_code, "
                    " income_category, amount) "
                    "VALUES (:w, :a, '2020-01-01', 'IT-2014-07', 'redditi_diversi', 500.00)"
                ),
                {"w": str(workspace_id), "a": str(account_id)},
            )

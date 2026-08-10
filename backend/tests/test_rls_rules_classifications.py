"""Test di sicurezza a livello di database per `rules` e `classifications`
(milestone 06) — stesso principio di test_rls_accounts_transactions.py:
bypassano completamente l'API e parlano direttamente con Postgres come
lumio_app, per provare che l'isolamento tiene anche se il codice
applicativo avesse un bug.
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


async def _create_account(user_id: uuid.UUID, workspace_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        account_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                    "VALUES (:w, 'Conto', 'checking', 'EUR') RETURNING id"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()
        await session.commit()
    return account_id


async def _create_transaction(user_id: uuid.UUID, workspace_id: uuid.UUID, account_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        transaction_id = (
            await session.execute(
                text(
                    "INSERT INTO transactions "
                    "(workspace_id, financial_account_id, transaction_date, description_raw, "
                    " amount, currency, direction, transaction_type) "
                    "VALUES (:w, :a, CURRENT_DATE, 'Spesa', -10.00, 'EUR', 'debit', 'expense') "
                    "RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()
    return transaction_id


async def _create_custom_category(user_id: uuid.UUID, workspace_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        category_id = (
            await session.execute(
                text(
                    "INSERT INTO categories (workspace_id, name, code) "
                    "VALUES (:w, 'Privata', 'privata') RETURNING id"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()
        await session.commit()
    return category_id


# --- rules -------------------------------------------------------------------


async def test_user_cannot_select_another_workspace_rule_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("rule-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("rule-rls-b@example.com")
    category_b = await _create_custom_category(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        rule_b = (
            await session.execute(
                text(
                    "INSERT INTO rules (workspace_id, name, field, operator, value, category_id) "
                    "VALUES (:w, 'Netflix', 'description', 'contains', 'netflix', :c) RETURNING id"
                ),
                {"w": str(workspace_b), "c": str(category_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        direct_lookup = await session.execute(
            text("SELECT id FROM rules WHERE id = :rid"), {"rid": str(rule_b)}
        )
        assert direct_lookup.first() is None


async def test_user_cannot_insert_rule_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("rule-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("rule-rls-d@example.com")
    category_b = await _create_custom_category(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO rules (workspace_id, name, field, operator, value, category_id) "
                    "VALUES (:w, 'Netflix', 'description', 'contains', 'netflix', :c)"
                ),
                {"w": str(workspace_b), "c": str(category_b)},
            )


async def test_rule_cannot_reference_category_of_another_workspace():
    user_a, workspace_a = await _create_user_with_workspace("rule-cat-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("rule-cat-b@example.com")
    category_b = await _create_custom_category(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO rules (workspace_id, name, field, operator, value, category_id) "
                    "VALUES (:w, 'Netflix', 'description', 'contains', 'netflix', :c)"
                ),
                {"w": str(workspace_a), "c": str(category_b)},
            )


# --- classifications -----------------------------------------------------------


async def test_user_cannot_select_another_workspace_classification_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("classif-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("classif-rls-b@example.com")
    account_b = await _create_account(user_b, workspace_b)
    transaction_b = await _create_transaction(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        classification_b = (
            await session.execute(
                text(
                    "INSERT INTO classifications (transaction_id, method) "
                    "VALUES (:t, 'manual') RETURNING id"
                ),
                {"t": str(transaction_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        direct_lookup = await session.execute(
            text("SELECT id FROM classifications WHERE id = :cid"), {"cid": str(classification_b)}
        )
        assert direct_lookup.first() is None


async def test_user_cannot_insert_classification_on_another_workspace_transaction_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("classif-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("classif-rls-d@example.com")
    account_b = await _create_account(user_b, workspace_b)
    transaction_b = await _create_transaction(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text("INSERT INTO classifications (transaction_id, method) VALUES (:t, 'manual')"),
                {"t": str(transaction_b)},
            )


async def test_classification_cannot_reference_category_of_another_workspace():
    user_a, workspace_a = await _create_user_with_workspace("classif-cat-a@example.com")
    account_a = await _create_account(user_a, workspace_a)
    transaction_a = await _create_transaction(user_a, workspace_a, account_a)
    user_b, workspace_b = await _create_user_with_workspace("classif-cat-b@example.com")
    category_b = await _create_custom_category(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO classifications (transaction_id, method, category_id) "
                    "VALUES (:t, 'user', :c)"
                ),
                {"t": str(transaction_a), "c": str(category_b)},
            )


async def test_classifications_cannot_be_updated_or_deleted_directly():
    # Storico immutabile per design: nessuna policy UPDATE/DELETE, quindi
    # con FORCE ROW LEVEL SECURITY entrambe le operazioni non trovano righe
    # da modificare per lumio_app, anche sul proprio workspace.
    user_a, workspace_a = await _create_user_with_workspace("classif-immutable-a@example.com")
    account_a = await _create_account(user_a, workspace_a)
    transaction_a = await _create_transaction(user_a, workspace_a, account_a)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        classification_a = (
            await session.execute(
                text(
                    "INSERT INTO classifications (transaction_id, method) "
                    "VALUES (:t, 'manual') RETURNING id"
                ),
                {"t": str(transaction_a)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        update_result = await session.execute(
            text("UPDATE classifications SET method = 'ai' WHERE id = :cid"),
            {"cid": str(classification_a)},
        )
        assert update_result.rowcount == 0

        delete_result = await session.execute(
            text("DELETE FROM classifications WHERE id = :cid"), {"cid": str(classification_a)}
        )
        assert delete_result.rowcount == 0

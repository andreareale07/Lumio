"""Test di sicurezza a livello di database per `transaction_dedup_decisions`
e `transaction_review_items` — stesso principio di test_rls_imports.py:
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
                    " amount, currency, direction, transaction_type, dedup_fingerprint) "
                    "VALUES (:w, :a, CURRENT_DATE, 'Spesa', -10.00, 'EUR', 'debit', 'expense', "
                    " 'rls-test-fingerprint') "
                    "RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()
    return transaction_id


async def _create_import(user_id: uuid.UUID, workspace_id: uuid.UUID, account_id: uuid.UUID) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        import_id = (
            await session.execute(
                text(
                    "INSERT INTO imports "
                    "(workspace_id, financial_account_id, created_by_user_id, filename, file_hash, file_size) "
                    "VALUES (:w, :a, :u, 'estratto.csv', :h, 100) RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id), "u": str(user_id), "h": uuid.uuid4().hex + uuid.uuid4().hex},
            )
        ).scalar_one()
        await session.commit()
    return import_id


async def _create_decision(
    user_id: uuid.UUID, workspace_id: uuid.UUID, account_id: uuid.UUID, transaction_id: uuid.UUID
) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        decision_id = (
            await session.execute(
                text(
                    "INSERT INTO transaction_dedup_decisions "
                    "(workspace_id, financial_account_id, existing_transaction_id, new_fingerprint, "
                    " decision, decided_by_user_id) "
                    "VALUES (:w, :a, :t, 'some-fingerprint', 'confirmed_distinct', :u) RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id), "t": str(transaction_id), "u": str(user_id)},
            )
        ).scalar_one()
        await session.commit()
    return decision_id


async def _create_review_item(
    user_id: uuid.UUID, workspace_id: uuid.UUID, account_id: uuid.UUID, import_id: uuid.UUID
) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        item_id = (
            await session.execute(
                text(
                    "INSERT INTO transaction_review_items "
                    "(workspace_id, import_id, financial_account_id, row_index, transaction_date, "
                    " description_raw, amount, currency, direction, transaction_type, new_fingerprint) "
                    "VALUES (:w, :i, :a, 0, CURRENT_DATE, 'Spesa ambigua', -10.00, 'EUR', 'debit', 'expense', "
                    " 'pending-fingerprint') RETURNING id"
                ),
                {"w": str(workspace_id), "i": str(import_id), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()
    return item_id


async def test_user_cannot_select_another_workspace_dedup_decision_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("dd-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("dd-rls-b@example.com")
    account_b = await _create_account(user_b, workspace_b)
    transaction_b = await _create_transaction(user_b, workspace_b, account_b)
    decision_b = await _create_decision(user_b, workspace_b, account_b, transaction_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM transaction_dedup_decisions WHERE id = :did"), {"did": str(decision_b)}
        )
        assert result.first() is None


async def test_user_cannot_insert_dedup_decision_into_another_workspace_via_rls():
    user_a, workspace_a = await _create_user_with_workspace("dd-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("dd-rls-d@example.com")
    account_b = await _create_account(user_b, workspace_b)
    transaction_b = await _create_transaction(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO transaction_dedup_decisions "
                    "(workspace_id, financial_account_id, existing_transaction_id, new_fingerprint, "
                    " decision, decided_by_user_id) "
                    "VALUES (:w, :a, :t, 'x', 'confirmed_distinct', :u)"
                ),
                {"w": str(workspace_a), "a": str(account_b), "t": str(transaction_b), "u": str(user_a)},
            )


async def test_user_cannot_select_another_workspace_review_item_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("ri-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("ri-rls-b@example.com")
    account_b = await _create_account(user_b, workspace_b)
    import_b = await _create_import(user_b, workspace_b, account_b)
    item_b = await _create_review_item(user_b, workspace_b, account_b, import_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM transaction_review_items WHERE id = :iid"), {"iid": str(item_b)}
        )
        assert result.first() is None


async def test_user_cannot_insert_review_item_into_another_workspace_via_rls():
    user_a, workspace_a = await _create_user_with_workspace("ri-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("ri-rls-d@example.com")
    account_b = await _create_account(user_b, workspace_b)
    import_b = await _create_import(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO transaction_review_items "
                    "(workspace_id, import_id, financial_account_id, row_index, transaction_date, "
                    " description_raw, amount, currency, direction, transaction_type, new_fingerprint) "
                    "VALUES (:w, :i, :a, 0, CURRENT_DATE, 'Spesa', -10.00, 'EUR', 'debit', 'expense', 'x')"
                ),
                {"w": str(workspace_a), "i": str(import_b), "a": str(account_b)},
            )


async def test_dedup_decision_unique_constraint_blocks_duplicate_pair():
    user_id, workspace_id = await _create_user_with_workspace("dd-unique-a@example.com")
    account_id = await _create_account(user_id, workspace_id)
    transaction_id = await _create_transaction(user_id, workspace_id, account_id)
    await _create_decision(user_id, workspace_id, account_id, transaction_id)

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO transaction_dedup_decisions "
                    "(workspace_id, financial_account_id, existing_transaction_id, new_fingerprint, "
                    " decision, decided_by_user_id) "
                    "VALUES (:w, :a, :t, 'some-fingerprint', 'confirmed_duplicate', :u)"
                ),
                {"w": str(workspace_id), "a": str(account_id), "t": str(transaction_id), "u": str(user_id)},
            )


async def test_review_item_cascades_on_import_delete():
    user_id, workspace_id = await _create_user_with_workspace("ri-cascade-a@example.com")
    account_id = await _create_account(user_id, workspace_id)
    import_id = await _create_import(user_id, workspace_id, account_id)
    item_id = await _create_review_item(user_id, workspace_id, account_id, import_id)

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        await session.execute(text("DELETE FROM imports WHERE id = :i"), {"i": str(import_id)})
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        result = await session.execute(
            text("SELECT id FROM transaction_review_items WHERE id = :iid"), {"iid": str(item_id)}
        )
        assert result.first() is None

"""Test di sicurezza a livello di database per `imports` e `import_mappings`
— stesso principio di test_rls_accounts_transactions.py: bypassano
completamente l'API e parlano direttamente con Postgres come lumio_app, per
provare che l'isolamento tiene anche se il codice applicativo avesse un bug.
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


async def _create_import(
    user_id: uuid.UUID, workspace_id: uuid.UUID, account_id: uuid.UUID, file_hash: str = "a" * 64
) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        import_id = (
            await session.execute(
                text(
                    "INSERT INTO imports "
                    "(workspace_id, financial_account_id, created_by_user_id, filename, "
                    " file_hash, file_size) "
                    "VALUES (:w, :a, :u, 'estratto.csv', :h, 100) RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id), "u": str(user_id), "h": file_hash},
            )
        ).scalar_one()
        await session.commit()
    return import_id


async def test_user_cannot_select_another_workspace_import_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("imp-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("imp-rls-b@example.com")
    account_b = await _create_account(user_b, workspace_b)
    import_b = await _create_import(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        direct_lookup = await session.execute(
            text("SELECT id FROM imports WHERE id = :iid"), {"iid": str(import_b)}
        )
        assert direct_lookup.first() is None


async def test_user_cannot_insert_import_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("imp-rls-c@example.com")
    user_b, workspace_b = await _create_user_with_workspace("imp-rls-d@example.com")
    account_b = await _create_account(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO imports "
                    "(workspace_id, financial_account_id, created_by_user_id, filename, "
                    " file_hash, file_size) "
                    "VALUES (:w, :a, :u, 'x.csv', :h, 1)"
                ),
                {"w": str(workspace_b), "a": str(account_b), "u": str(user_a), "h": "b" * 64},
            )


async def test_import_cannot_reference_account_of_another_workspace():
    # Non e' un test di RLS ma della FK composita (workspace_id,
    # financial_account_id) -> financial_accounts(workspace_id, id).
    user_a, workspace_a = await _create_user_with_workspace("imp-fk-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("imp-fk-b@example.com")
    account_b = await _create_account(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO imports "
                    "(workspace_id, financial_account_id, created_by_user_id, filename, "
                    " file_hash, file_size) "
                    "VALUES (:w, :a, :u, 'x.csv', :h, 1)"
                ),
                {"w": str(workspace_a), "a": str(account_b), "u": str(user_a), "h": "c" * 64},
            )


async def test_transaction_cannot_reference_import_of_another_workspace():
    user_a, workspace_a = await _create_user_with_workspace("tx-imp-a@example.com")
    account_a = await _create_account(user_a, workspace_a)
    user_b, workspace_b = await _create_user_with_workspace("tx-imp-b@example.com")
    account_b = await _create_account(user_b, workspace_b)
    import_b = await _create_import(user_b, workspace_b, account_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO transactions "
                    "(workspace_id, financial_account_id, import_id, transaction_date, "
                    " description_raw, amount, currency, direction, transaction_type, dedup_fingerprint) "
                    "VALUES (:w, :a, :i, CURRENT_DATE, 'Spesa', -10.00, 'EUR', 'debit', 'expense', "
                    " 'rls-test-fingerprint')"
                ),
                {"w": str(workspace_a), "a": str(account_a), "i": str(import_b)},
            )


async def test_user_cannot_select_another_workspace_mapping_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("map-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("map-rls-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        mapping_b = (
            await session.execute(
                text(
                    "INSERT INTO import_mappings (workspace_id, name, config) "
                    "VALUES (:w, 'Mia mappatura', '{}'::jsonb) RETURNING id"
                ),
                {"w": str(workspace_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        direct_lookup = await session.execute(
            text("SELECT id FROM import_mappings WHERE id = :mid"), {"mid": str(mapping_b)}
        )
        assert direct_lookup.first() is None


async def test_mapping_cannot_reference_account_of_another_workspace():
    user_a, workspace_a = await _create_user_with_workspace("map-fk-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("map-fk-b@example.com")
    account_b = await _create_account(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO import_mappings (workspace_id, financial_account_id, name, config) "
                    "VALUES (:w, :a, 'x', '{}'::jsonb)"
                ),
                {"w": str(workspace_a), "a": str(account_b)},
            )


async def test_import_dedup_unique_index_blocks_second_active_import_same_hash():
    user_a, workspace_a = await _create_user_with_workspace("dedup-a@example.com")
    account_a = await _create_account(user_a, workspace_a)
    file_hash = "d" * 64
    await _create_import(user_a, workspace_a, account_a, file_hash=file_hash)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="uq_imports_workspace_file_hash_active"):
            await session.execute(
                text(
                    "INSERT INTO imports "
                    "(workspace_id, financial_account_id, created_by_user_id, filename, "
                    " file_hash, file_size) "
                    "VALUES (:w, :a, :u, 'y.csv', :h, 1)"
                ),
                {"w": str(workspace_a), "a": str(account_a), "u": str(user_a), "h": file_hash},
            )


async def test_import_dedup_allows_reupload_after_failed():
    user_a, workspace_a = await _create_user_with_workspace("dedup-b@example.com")
    account_a = await _create_account(user_a, workspace_a)
    file_hash = "e" * 64
    first_id = await _create_import(user_a, workspace_a, account_a, file_hash=file_hash)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        await session.execute(
            text("UPDATE imports SET status = 'failed' WHERE id = :iid"), {"iid": str(first_id)}
        )
        await session.commit()

    # Un secondo import con lo stesso hash e' ammesso: l'indice unico
    # parziale esclude gli stati failed/cancelled.
    second_id = await _create_import(user_a, workspace_a, account_a, file_hash=file_hash)
    assert second_id != first_id

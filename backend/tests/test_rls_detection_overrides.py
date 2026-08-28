"""Test di sicurezza a livello di database per `detection_overrides` —
stesso principio di `test_rls_transaction_dedup.py`: bypassano
completamente l'API e parlano direttamente con Postgres come `lumio_app`,
per provare che l'isolamento tiene anche se il codice applicativo avesse un
bug."""
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
                    " 'rls-detection-test-fingerprint') "
                    "RETURNING id"
                ),
                {"w": str(workspace_id), "a": str(account_id)},
            )
        ).scalar_one()
        await session.commit()
    return transaction_id


async def _create_recurring_override(
    user_id: uuid.UUID, workspace_id: uuid.UUID, series_key: str
) -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        override_id = (
            await session.execute(
                text(
                    "INSERT INTO detection_overrides "
                    "(workspace_id, override_type, series_key, decision, created_by_user_id) "
                    "VALUES (:w, 'recurring_series', :sk, 'ignored', :u) RETURNING id"
                ),
                {"w": str(workspace_id), "sk": series_key, "u": str(user_id)},
            )
        ).scalar_one()
        await session.commit()
    return override_id


async def test_user_cannot_select_another_workspace_override_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("do-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("do-rls-b@example.com")
    override_b = await _create_recurring_override(user_b, workspace_b, "series-key-b")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(
            text("SELECT id FROM detection_overrides WHERE id = :oid"), {"oid": str(override_b)}
        )
        assert result.first() is None


async def test_user_cannot_insert_override_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("do-rls-c@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("do-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        # user_a autenticato, ma il target e' workspace_b (di user_b): la
        # WITH CHECK di is_workspace_member(workspace_id) deve rifiutarla —
        # prima di questa correzione il test inseriva per errore in
        # workspace_a (il workspace di user_a stesso), che RLS ammette
        # correttamente, mascherando un test che non provava nulla.
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO detection_overrides "
                    "(workspace_id, override_type, series_key, decision, created_by_user_id) "
                    "VALUES (:w, 'recurring_series', 'x', 'ignored', :u)"
                ),
                {"w": str(workspace_b), "u": str(user_a)},
            )


async def test_check_constraint_rejects_mismatched_target_for_type():
    user_id, workspace_id = await _create_user_with_workspace("do-check-a@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO detection_overrides "
                    "(workspace_id, override_type, series_key, transaction_id, decision, created_by_user_id) "
                    "VALUES (:w, 'anomaly', 'should-be-null', NULL, 'ignored', :u)"
                ),
                {"w": str(workspace_id), "u": str(user_id)},
            )


async def test_check_constraint_rejects_invalid_decision():
    user_id, workspace_id = await _create_user_with_workspace("do-check-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO detection_overrides "
                    "(workspace_id, override_type, series_key, decision, created_by_user_id) "
                    "VALUES (:w, 'recurring_series', 'x', 'not-a-real-decision', :u)"
                ),
                {"w": str(workspace_id), "u": str(user_id)},
            )


async def test_partial_unique_index_blocks_duplicate_recurring_series_override():
    user_id, workspace_id = await _create_user_with_workspace("do-unique-a@example.com")
    await _create_recurring_override(user_id, workspace_id, "duplicate-series-key")

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO detection_overrides "
                    "(workspace_id, override_type, series_key, decision, created_by_user_id) "
                    "VALUES (:w, 'recurring_series', 'duplicate-series-key', 'ignored', :u)"
                ),
                {"w": str(workspace_id), "u": str(user_id)},
            )


async def test_override_cascades_on_transaction_delete():
    user_id, workspace_id = await _create_user_with_workspace("do-cascade-a@example.com")
    account_id = await _create_account(user_id, workspace_id)
    transaction_id = await _create_transaction(user_id, workspace_id, account_id)

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        override_id = (
            await session.execute(
                text(
                    "INSERT INTO detection_overrides "
                    "(workspace_id, override_type, transaction_id, decision, created_by_user_id) "
                    "VALUES (:w, 'anomaly', :t, 'ignored', :u) RETURNING id"
                ),
                {"w": str(workspace_id), "t": str(transaction_id), "u": str(user_id)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        await session.execute(text("DELETE FROM transactions WHERE id = :t"), {"t": str(transaction_id)})
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        result = await session.execute(
            text("SELECT id FROM detection_overrides WHERE id = :oid"), {"oid": str(override_id)}
        )
        assert result.first() is None

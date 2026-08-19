"""Test di sicurezza a livello di database per financial_accounts,
categories, transactions — stesso principio di test_rls_workspaces.py:
bypassano completamente l'API e parlano direttamente con Postgres come
lumio_app, per provare che l'isolamento tiene anche se il codice
applicativo avesse un bug.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.base import async_session_factory
from app.db.seed_data import SYSTEM_CATEGORIES

_SYSTEM_CATEGORY_ID = uuid.UUID(SYSTEM_CATEGORIES[0]["id"])


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


async def test_user_cannot_select_another_workspace_account_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("acc-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("acc-rls-b@example.com")
    account_b = await _create_account(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        direct_lookup = await session.execute(
            text("SELECT id FROM financial_accounts WHERE id = :aid"), {"aid": str(account_b)}
        )
        assert direct_lookup.first() is None


async def test_user_cannot_insert_account_into_another_workspace_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("acc-rls-c@example.com")
    _, workspace_b = await _create_user_with_workspace("acc-rls-d@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                    "VALUES (:w, 'Conto', 'checking', 'EUR')"
                ),
                {"w": str(workspace_b)},
            )


async def test_user_cannot_select_another_workspace_transaction_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("tx-rls-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("tx-rls-b@example.com")
    account_b = await _create_account(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        transaction_b = (
            await session.execute(
                text(
                    "INSERT INTO transactions "
                    "(workspace_id, financial_account_id, transaction_date, description_raw, "
                    " amount, currency, direction, transaction_type, dedup_fingerprint) "
                    "VALUES (:w, :a, CURRENT_DATE, 'Spesa', -10.00, 'EUR', 'debit', 'expense', "
                    " 'rls-test-fingerprint') "
                    "RETURNING id"
                ),
                {"w": str(workspace_b), "a": str(account_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        direct_lookup = await session.execute(
            text("SELECT id FROM transactions WHERE id = :tid"), {"tid": str(transaction_b)}
        )
        assert direct_lookup.first() is None


async def test_transaction_cannot_reference_account_of_another_workspace():
    # Non e' un test di RLS ma della FK composita (workspace_id,
    # financial_account_id) -> financial_accounts(workspace_id, id): anche
    # se un bug applicativo permettesse di costruire questo INSERT con lo
    # workspace_id "giusto" ma un conto di un altro workspace, il vincolo DB
    # lo blocca comunque (SPEC §57).
    user_a, workspace_a = await _create_user_with_workspace("tx-fk-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("tx-fk-b@example.com")
    account_b = await _create_account(user_b, workspace_b)

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO transactions "
                    "(workspace_id, financial_account_id, transaction_date, description_raw, "
                    " amount, currency, direction, transaction_type, dedup_fingerprint) "
                    "VALUES (:w, :a, CURRENT_DATE, 'Spesa', -10.00, 'EUR', 'debit', 'expense', "
                    " 'rls-test-fingerprint')"
                ),
                {"w": str(workspace_a), "a": str(account_b)},
            )


async def test_transaction_cannot_reference_category_of_another_workspace():
    # category_id non ha una FK composita (le system category hanno
    # workspace_id NULL), quindi l'isolamento cross-tenant qui si affida
    # all'interazione FK+RLS: il vincolo FK viene valutato con lo stesso
    # ruolo della sessione, che non vede (per RLS) la categoria privata
    # dell'altro workspace, quindi il vincolo fallisce come se la riga non
    # esistesse.
    user_a, workspace_a = await _create_user_with_workspace("tx-cat-a@example.com")
    account_a = await _create_account(user_a, workspace_a)
    user_b, workspace_b = await _create_user_with_workspace("tx-cat-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        category_b = (
            await session.execute(
                text(
                    "INSERT INTO categories (workspace_id, name, code) "
                    "VALUES (:w, 'Privata', 'privata') RETURNING id"
                ),
                {"w": str(workspace_b)},
            )
        ).scalar_one()
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO transactions "
                    "(workspace_id, financial_account_id, category_id, transaction_date, "
                    " description_raw, amount, currency, direction, transaction_type, dedup_fingerprint) "
                    "VALUES (:w, :a, :c, CURRENT_DATE, 'Spesa', -10.00, 'EUR', 'debit', 'expense', "
                    " 'rls-test-fingerprint')"
                ),
                {"w": str(workspace_a), "a": str(account_a), "c": str(category_b)},
            )


async def test_system_category_visible_to_everyone_but_not_writable():
    user_a, _workspace_a = await _create_user_with_workspace("cat-sys-a@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        visible = await session.execute(
            text("SELECT id FROM categories WHERE id = :cid"), {"cid": str(_SYSTEM_CATEGORY_ID)}
        )
        assert visible.first() is not None

        # La USING clause di categories_update richiede workspace_id NOT
        # NULL: per una system category e' sempre falsa, quindi Postgres non
        # solleva un errore di RLS (a differenza di un INSERT bloccato dalla
        # WITH CHECK) — semplicemente non trova righe da aggiornare. E'
        # comunque la protezione corretta: la riga resta invariata.
        update_result = await session.execute(
            text("UPDATE categories SET name = 'Hacked' WHERE id = :cid"),
            {"cid": str(_SYSTEM_CATEGORY_ID)},
        )
        assert update_result.rowcount == 0

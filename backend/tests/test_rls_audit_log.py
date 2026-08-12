"""Test di sicurezza a livello di database per `audit_log` (milestone 11,
SPEC §56/59) — stesso principio di `test_rls_job_runs.py`: bypassano
completamente l'API e parlano direttamente con Postgres come lumio_app.

A differenza di ogni altra tabella RLS del progetto, qui si verifica anche
l'ASSENZA delle policy UPDATE/DELETE (append-only per design)."""
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


async def _insert_audit_row(session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    return (
        await session.execute(
            text(
                "INSERT INTO audit_log (workspace_id, user_id, event_type, entity_type) "
                "VALUES (:w, :u, 'LOGIN', 'user') RETURNING id"
            ),
            {"w": str(workspace_id), "u": str(user_id)},
        )
    ).scalar_one()


async def test_user_cannot_insert_audit_log_into_another_workspace():
    user_a, _workspace_a = await _create_user_with_workspace("audit-rls-insert-a@example.com")
    _user_b, workspace_b = await _create_user_with_workspace("audit-rls-insert-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await _insert_audit_row(session, workspace_b, user_a)


async def test_user_cannot_select_another_workspace_audit_log_via_rls():
    user_a, _workspace_a = await _create_user_with_workspace("audit-rls-select-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("audit-rls-select-b@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_b)
        row_id = await _insert_audit_row(session, workspace_b, user_b)
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(text("SELECT id FROM audit_log WHERE id = :id"), {"id": str(row_id)})
        assert result.first() is None


async def test_audit_log_has_no_update_or_delete_policy():
    """Append-only per design (SPEC §59) — un membro del workspace non deve
    poter alterare o rimuovere una riga di audit gia' scritta, nemmeno la
    propria.

    Senza una policy per un comando, Postgres NON solleva un errore su
    UPDATE/DELETE (a differenza di INSERT/SELECT, dove qui c'e' una policy
    esplicita che nega): il default e' un "USING (false)" implicito, quindi
    il comando va a buon fine ma non tocca alcuna riga — e' questo che va
    verificato, non un'eccezione."""
    user_a, workspace_a = await _create_user_with_workspace("audit-rls-immutable@example.com")

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        row_id = await _insert_audit_row(session, workspace_a, user_a)
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        update_result = await session.execute(
            text("UPDATE audit_log SET event_type = 'RULE_CREATED' WHERE id = :id"), {"id": str(row_id)}
        )
        assert update_result.rowcount == 0
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        delete_result = await session.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": str(row_id)})
        assert delete_result.rowcount == 0
        await session.commit()

    async with async_session_factory() as session:
        await _set_current_user(session, user_a)
        result = await session.execute(text("SELECT event_type FROM audit_log WHERE id = :id"), {"id": str(row_id)})
        assert result.scalar_one() == "LOGIN"

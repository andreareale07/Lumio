"""Unit test di `audit_log_service.log_event` (milestone 11) — verifica che
la funzione componga correttamente la riga e la accodi alla sessione senza
commit proprio (il commit resta responsabilita' del chiamante, come ogni
altro service DB-aware del progetto)."""
import uuid

from sqlalchemy import text

from app.db.base import async_session_factory
from app.services.audit_log_service import log_event


async def test_log_event_adds_row_visible_after_caller_commits():
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        await session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name) "
                "VALUES (:id, 'audit-service@example.com', 'x', 'Test')"
            ),
            {"id": str(user_id)},
        )
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

        await log_event(
            session, workspace_id, user_id, "RULE_CREATED",
            entity_type="rule", entity_id=uuid.uuid4(), metadata={"note": "test"},
        )
        await session.commit()

    # Nuova sessione (identita' fresca): SET LOCAL app.current_user_id scade
    # al commit sopra (vedi app/db/rls.py), quindi una query RLS-dipendente
    # sulla STESSA sessione dopo quel commit girerebbe senza identita'
    # impostata e le policy negherebbero tutto — stesso gotcha documentato
    # in memoria/altri test, verificato empiricamente qui pure.
    async with async_session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        result = await session.execute(
            text("SELECT event_type, entity_type, metadata FROM audit_log WHERE workspace_id = :w"),
            {"w": str(workspace_id)},
        )
        row = result.mappings().one()
        assert row["event_type"] == "RULE_CREATED"
        assert row["entity_type"] == "rule"
        assert row["metadata"] == {"note": "test"}

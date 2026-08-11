"""Test del tracciamento di stato dei job async (gap UX emerso testando
M09b, vedi memoria di progetto): app/services/job_run_tracker.py. Stesso
pattern DB-diretto di test_rls_market_data.py per creare rapidamente un
workspace di test, senza passare dall'API.
"""
import uuid

import pytest
from sqlalchemy import text

from app.db.base import async_session_factory
from app.services.job_run_tracker import finish_run, get_latest_run, start_run, tracked_job_run


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


async def _fetch_latest(user_id: uuid.UUID, workspace_id: uuid.UUID, job_kind: str):
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        return await get_latest_run(session, workspace_id, job_kind)


async def test_get_latest_run_returns_none_when_never_run():
    user_id, workspace_id = await _create_user_with_workspace("jr-never@example.com")
    run = await _fetch_latest(user_id, workspace_id, "market_data_refresh")
    assert run is None


async def test_start_run_then_finish_run_success():
    user_id, workspace_id = await _create_user_with_workspace("jr-success@example.com")

    await start_run(workspace_id, user_id, "market_data_refresh", job_id="job-1")
    running = await _fetch_latest(user_id, workspace_id, "market_data_refresh")
    assert running.status == "running"
    assert running.finished_at is None

    await finish_run(
        workspace_id, user_id, "market_data_refresh", success=True, message="3 prezzi aggiornati su 3 asset."
    )
    done = await _fetch_latest(user_id, workspace_id, "market_data_refresh")
    assert done.status == "success"
    assert done.finished_at is not None
    assert done.message == "3 prezzi aggiornati su 3 asset."


async def test_second_run_overwrites_the_same_row_not_a_new_one():
    """Una sola riga per (workspace, job_kind): la vecchia esecuzione non
    lascia traccia, e' proprio lo stato minimo richiesto (non uno storico)."""
    user_id, workspace_id = await _create_user_with_workspace("jr-overwrite@example.com")

    await start_run(workspace_id, user_id, "market_data_refresh")
    await finish_run(workspace_id, user_id, "market_data_refresh", success=True, message="ok")
    await start_run(workspace_id, user_id, "market_data_refresh")
    await finish_run(workspace_id, user_id, "market_data_refresh", success=False, message="errore di rete")

    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        rows = (
            await session.execute(
                text("SELECT status, message FROM job_runs WHERE workspace_id = :w"), {"w": str(workspace_id)}
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].message == "errore di rete"


async def test_job_kinds_are_tracked_independently():
    user_id, workspace_id = await _create_user_with_workspace("jr-independent@example.com")

    await start_run(workspace_id, user_id, "market_data_refresh")
    await finish_run(workspace_id, user_id, "market_data_refresh", success=True, message="prezzi ok")

    snapshot_run = await _fetch_latest(user_id, workspace_id, "snapshot_rebuild")
    assert snapshot_run is None  # non ancora eseguito, indipendente dall'altro job_kind


async def test_tracked_job_run_sets_running_then_success_with_handle_message():
    user_id, workspace_id = await _create_user_with_workspace("jr-context@example.com")

    async with tracked_job_run(workspace_id, user_id, "snapshot_rebuild") as run:
        mid_run = await _fetch_latest(user_id, workspace_id, "snapshot_rebuild")
        assert mid_run.status == "running"
        run.message = "Snapshot ricalcolato per il 2026-08-11 (2 portfolio)."

    final_run = await _fetch_latest(user_id, workspace_id, "snapshot_rebuild")
    assert final_run.status == "success"
    assert final_run.message == "Snapshot ricalcolato per il 2026-08-11 (2 portfolio)."


async def test_tracked_job_run_records_failure_and_reraises():
    user_id, workspace_id = await _create_user_with_workspace("jr-fail@example.com")

    with pytest.raises(ValueError, match="boom"):
        async with tracked_job_run(workspace_id, user_id, "snapshot_rebuild"):
            raise ValueError("boom")

    run = await _fetch_latest(user_id, workspace_id, "snapshot_rebuild")
    assert run.status == "failed"
    assert run.message == "boom"

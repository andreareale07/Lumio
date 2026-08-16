"""Rilevatore generico di job bloccati (app/services/job_health.py) — verifica
che il motore, comune a tutti i tipi di job, marchi correttamente falliti gli
stati non-terminali piu' vecchi della soglia configurata in `system_settings`,
lasci intatto cio' che e' ancora "fresco", e che le soglie siano davvero
lette da quella tabella (non cablate), visto che e' esattamente il requisito
per cui e' stata introdotta.
"""
import json
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import text

from app.db.base import async_session_factory
from app.models.job_run import JobRun
from app.services.job_health import expire_stale_jobs


async def _register(client: AsyncClient, email: str) -> tuple[str, str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    body = response.json()
    return body["access_token"], body["user"]["id"], body["user"]["workspace_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def _create_import_row(
    workspace_id: str,
    account_id: str,
    user_id: str,
    status: str,
    ai_classification_status: str | None,
    updated_at: datetime,
) -> str:
    """Inserisce direttamente una riga `imports` con lo stato/timestamp voluti
    — non esiste un percorso API per mettere un import in uno stato
    intermedio "bloccato da ore" senza aspettare davvero ore, stesso
    approccio di `_set_import_status` in test_imports.py."""
    import_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id})
        await session.execute(
            text(
                "INSERT INTO imports (id, workspace_id, financial_account_id, created_by_user_id, "
                "status, filename, file_hash, file_size, ai_classification_status, updated_at) "
                "VALUES (:id, :ws, :acc, :uid, :status, 'test.csv', :hash, 10, :ai_status, :updated_at)"
            ),
            {
                "id": import_id,
                "ws": workspace_id,
                "acc": account_id,
                "uid": user_id,
                "status": status,
                "hash": uuid.uuid4().hex,
                "ai_status": ai_classification_status,
                "updated_at": updated_at,
            },
        )
        await session.commit()
    return import_id


async def _set_setting(key: str, value) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text("UPDATE system_settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
            {"v": json.dumps(value), "k": key},
        )
        await session.commit()


async def _get_setting(key: str):
    async with async_session_factory() as session:
        row = (await session.execute(text("SELECT value FROM system_settings WHERE key = :k"), {"k": key})).first()
        return row[0] if row else None


async def test_stale_import_gets_marked_failed(client):
    token, user_id, workspace_id = await _register(client, "job-health-import@example.com")
    account_id = await _create_account(client, token)
    import_id = await _create_import_row(
        workspace_id,
        account_id,
        user_id,
        status="processing",
        ai_classification_status=None,
        updated_at=datetime.now(UTC) - timedelta(seconds=10_000),
    )
    await _set_setting("job_health.import.stale_after_seconds", 420)

    totals = await expire_stale_jobs()
    assert totals["import"] >= 1

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["status"] == "failed"
    assert detail.json()["error_message"]


async def test_fresh_import_is_left_untouched(client):
    token, user_id, workspace_id = await _register(client, "job-health-fresh@example.com")
    account_id = await _create_account(client, token)
    import_id = await _create_import_row(
        workspace_id,
        account_id,
        user_id,
        status="processing",
        ai_classification_status=None,
        updated_at=datetime.now(UTC),  # "adesso": un job legittimamente in corso non va mai toccato
    )
    await _set_setting("job_health.import.stale_after_seconds", 420)

    await expire_stale_jobs()

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["status"] == "processing"


async def test_stale_ai_classification_gets_marked_failed(client):
    token, user_id, workspace_id = await _register(client, "job-health-ai@example.com")
    account_id = await _create_account(client, token)
    import_id = await _create_import_row(
        workspace_id,
        account_id,
        user_id,
        status="completed",
        ai_classification_status="running",
        updated_at=datetime.now(UTC) - timedelta(seconds=10_000),
    )
    await _set_setting("job_health.ai_classification.stale_after_seconds", 120)

    totals = await expire_stale_jobs()
    assert totals["ai_classification"] >= 1

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["ai_classification_status"] == "failed"
    # L'import stesso resta 'completed': il crash della classificazione AI
    # non deve retrocedere lo stato dell'import principale.
    assert detail.json()["status"] == "completed"


async def test_threshold_is_read_from_system_settings_not_hardcoded(client):
    """Verifica il requisito esplicito: la soglia non e' cablata nel codice
    — cambiandola in system_settings, lo stesso scenario passa da "non
    ancora stantio" a "stantio" senza toccare una riga di codice."""
    token, user_id, workspace_id = await _register(client, "job-health-threshold@example.com")
    account_id = await _create_account(client, token)
    import_id = await _create_import_row(
        workspace_id,
        account_id,
        user_id,
        status="processing",
        ai_classification_status=None,
        updated_at=datetime.now(UTC) - timedelta(seconds=500),
    )

    original = await _get_setting("job_health.import.stale_after_seconds")
    try:
        await _set_setting("job_health.import.stale_after_seconds", 10_000)  # soglia larga: non ancora stantio
        await expire_stale_jobs()
        detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
        assert detail.json()["status"] == "processing"

        await _set_setting("job_health.import.stale_after_seconds", 100)  # soglia stretta: ora e' stantio
        await expire_stale_jobs()
        detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
        assert detail.json()["status"] == "failed"
    finally:
        await _set_setting("job_health.import.stale_after_seconds", original)


async def test_stale_job_run_gets_marked_failed(client):
    token, user_id, workspace_id = await _register(client, "job-health-jobrun@example.com")
    job_run_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id})
        await session.execute(
            text(
                "INSERT INTO job_runs (id, workspace_id, job_kind, status, started_at) "
                "VALUES (:id, :ws, 'market_data_refresh', 'running', :started_at)"
            ),
            {"id": job_run_id, "ws": workspace_id, "started_at": datetime.now(UTC) - timedelta(seconds=10_000)},
        )
        await session.commit()
    await _set_setting("job_health.market_data_refresh.stale_after_seconds", 420)

    totals = await expire_stale_jobs()
    assert totals["market_data_refresh"] >= 1

    async with async_session_factory() as session:
        # `job_runs` e' RLS-protetta: senza impostare l'identita' anche qui,
        # `current_setting('app.current_user_id')` sulla connessione riusata
        # dal pool torna vuoto ("") invece di sollevare, e il cast a uuid
        # dentro la policy fallisce con un errore fuorviante.
        await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id})
        job_run = await session.get(JobRun, uuid.UUID(job_run_id))
    assert job_run.status == "failed"

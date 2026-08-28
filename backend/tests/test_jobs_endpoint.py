"""GET /api/v1/jobs (pagina Impostazioni > Job) + guardia enabled/disabled
nei job cron — il toggle riguarda SOLO l'esecuzione automatica schedulata,
mai il trigger manuale (decisione esplicita presa con l'utente).
"""
import json

from httpx import AsyncClient
from sqlalchemy import text

from app.db.base import async_session_factory
from app.worker.jobs.market_data import refresh_market_data_for_workspace, refresh_market_data_job


async def _register(client: AsyncClient, email: str) -> tuple[str, str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    body = response.json()
    return body["access_token"], body["user"]["id"], body["user"]["workspace_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _set_setting(key: str, value) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text("UPDATE system_settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
            {"v": json.dumps(value), "k": key},
        )
        await session.commit()


async def test_list_jobs_returns_eight_jobs_in_two_categories(client):
    token, _, _ = await _register(client, "jobs-list@example.com")
    response = await client.get("/api/v1/jobs", headers=_auth_headers(token))
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 8

    by_kind = {j["kind"]: j for j in jobs}
    scheduled = {"market_data_refresh", "snapshot_rebuild", "stale_job_reaper"}
    # "reclassification" (rework pipeline di classificazione): nuovo job
    # triggerabile manualmente, stesso principio di import/ai_classification.
    # "snapshot_backfill" (FETTA 3, storico patrimonio ricostruito): idem,
    # aggiunto in app/services/job_registry.py senza che questo test venisse
    # aggiornato di conseguenza (da qui il conteggio 7 -> 8).
    triggered = {
        "import", "ai_classification", "google_sheets_export", "reclassification", "snapshot_backfill",
    }
    assert {k for k, j in by_kind.items() if j["category"] == "scheduled"} == scheduled
    assert {k for k, j in by_kind.items() if j["category"] == "triggered"} == triggered

    # Scheduled: enabled e' un booleano reale, con la chiave da usare per il
    # PATCH generico gia' esistente. Triggered: nessun on/off qui.
    for kind in scheduled:
        assert isinstance(by_kind[kind]["enabled"], bool)
        assert by_kind[kind]["enabled_setting_key"] == f"jobs.{kind}.enabled"
        # La cadenza stessa e' fissa nel codice del worker (arq registra i
        # cron una sola volta all'avvio) — mai presentata come modificabile.
        assert by_kind[kind]["schedule_description_key"]
        assert by_kind[kind]["schedule_readonly_reason_key"]
    for kind in triggered:
        assert by_kind[kind]["enabled"] is None
        assert by_kind[kind]["enabled_setting_key"] is None
        assert by_kind[kind]["schedule_description_key"] is None

    # Ogni job ha almeno un parametro, e ogni parametro editabile porta la
    # chiave system_settings corretta per il PATCH.
    for job in jobs:
        assert len(job["parameters"]) > 0
        for param in job["parameters"]:
            if param["editable"]:
                assert param["setting_key"] is not None
            else:
                assert param["readonly_reason_key"] is not None


async def test_toggling_job_enabled_via_patch_is_reflected_in_jobs_list(client):
    token, _, _ = await _register(client, "jobs-toggle@example.com")
    key = "jobs.market_data_refresh.enabled"

    patch_resp = await client.patch(f"/api/v1/system-settings/{key}", json={"value": False}, headers=_auth_headers(token))
    assert patch_resp.status_code == 200

    jobs = (await client.get("/api/v1/jobs", headers=_auth_headers(token))).json()
    market_data_job = next(j for j in jobs if j["kind"] == "market_data_refresh")
    assert market_data_job["enabled"] is False

    await _set_setting(key, True)  # ripristino, la riga e' condivisa tra i test


async def test_disabled_market_data_cron_skips_scheduled_run_but_manual_trigger_still_works(client):
    token, user_id, workspace_id = await _register(client, "jobs-md-disabled@example.com")
    await _set_setting("jobs.market_data_refresh.enabled", False)

    try:
        # Il cron schedulato: con il flag disattivato, non deve nemmeno
        # creare la riga job_runs (si ferma prima di iterare i workspace).
        await refresh_market_data_job(None)
        async with async_session_factory() as session:
            await session.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id}
            )
            result = await session.execute(
                text("SELECT count(*) FROM job_runs WHERE workspace_id = :ws"), {"ws": workspace_id}
            )
            assert result.scalar_one() == 0

        # Il trigger MANUALE (bottone "Aggiorna ora") non e' toccato dal
        # flag — decisione esplicita: il flag riguarda solo l'automatismo.
        await refresh_market_data_for_workspace(None, workspace_id, user_id)
        status_resp = await client.get(
            "/api/v1/settings/market-data/refresh-status", headers=_auth_headers(token)
        )
        assert status_resp.json() is not None
        assert status_resp.json()["status"] == "success"
    finally:
        await _set_setting("jobs.market_data_refresh.enabled", True)

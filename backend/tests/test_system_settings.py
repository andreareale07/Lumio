"""GET/PATCH /system-settings — configurazione di ISTANZA (nessun workspace,
vedi app/models/system_setting.py). Nessun controllo di ruolo oggi (accettato
esplicitamente in attesa del futuro rework admin/utente): qui si verifica
solo che l'endpoint funzioni e che la validazione minima di tipo regga,
non un controllo di autorizzazione che ancora non esiste.
"""
import json

from httpx import AsyncClient
from sqlalchemy import text

from app.db.base import async_session_factory


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _restore_setting(key: str, value) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text("UPDATE system_settings SET value = CAST(:v AS jsonb) WHERE key = :k"),
            {"v": json.dumps(value), "k": key},
        )
        await session.commit()


async def test_list_system_settings_includes_seeded_job_health_thresholds(client):
    token = await _register(client, "settings-list@example.com")
    response = await client.get("/api/v1/system-settings", headers=_auth_headers(token))
    assert response.status_code == 200
    keys = {row["key"] for row in response.json()}
    assert "job_health.import.stale_after_seconds" in keys
    assert "job_health.ai_classification.stale_after_seconds" in keys
    assert "job_health.market_data_refresh.stale_after_seconds" in keys
    assert "job_health.snapshot_rebuild.stale_after_seconds" in keys
    assert "job_health.google_sheets_export.stale_after_seconds" in keys
    assert "jobs.market_data_refresh.enabled" in keys
    assert "jobs.snapshot_rebuild.enabled" in keys
    assert "jobs.stale_job_reaper.enabled" in keys


async def test_patch_system_setting_updates_value(client):
    token = await _register(client, "settings-patch@example.com")
    key = "job_health.import.stale_after_seconds"
    original = next(
        row["value"]
        for row in (await client.get("/api/v1/system-settings", headers=_auth_headers(token))).json()
        if row["key"] == key
    )
    try:
        response = await client.patch(
            f"/api/v1/system-settings/{key}", json={"value": 999}, headers=_auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json()["value"] == 999

        refetched = await client.get("/api/v1/system-settings", headers=_auth_headers(token))
        assert next(row["value"] for row in refetched.json() if row["key"] == key) == 999
    finally:
        await _restore_setting(key, original)


async def test_patch_unknown_setting_returns_404(client):
    token = await _register(client, "settings-404@example.com")
    response = await client.patch(
        "/api/v1/system-settings/does.not.exist", json={"value": 1}, headers=_auth_headers(token)
    )
    assert response.status_code == 404


async def test_patch_setting_rejects_type_mismatch(client):
    token = await _register(client, "settings-type@example.com")
    key = "job_health.import.stale_after_seconds"
    response = await client.patch(
        f"/api/v1/system-settings/{key}", json={"value": "not-a-number"}, headers=_auth_headers(token)
    )
    assert response.status_code == 400


async def test_patch_setting_rejects_non_positive_number(client):
    token = await _register(client, "settings-nonpositive@example.com")
    key = "job_health.import.stale_after_seconds"
    response = await client.patch(f"/api/v1/system-settings/{key}", json={"value": 0}, headers=_auth_headers(token))
    assert response.status_code == 400

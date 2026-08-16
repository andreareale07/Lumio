"""Job disaccoppiato di classificazione AI (rework "disaccoppiamento AI",
vedi worker/jobs/ai_classification_job.py) — copre lo stesso bug di
CancelledError-non-catturata gia' corretto in import_job.py: asyncio.
CancelledError eredita da BaseException (Python 3.8+), un `except
Exception:` la lascerebbe passare senza pulizia, lasciando l'import bloccato
per sempre in ai_classification_status='running'.
"""
import asyncio

from httpx import AsyncClient

from app.worker.jobs import ai_classification_job
from app.worker.jobs.ai_classification_job import classify_import_transactions_job
from app.worker.jobs.import_job import import_job

CSV_SAMPLE = "data,descrizione,importo\n2026-01-15,Pagamento NETFLIX.COM,-12.99\n"


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def test_classify_import_transactions_job_marks_failed_and_reraises_on_cancellation(
    client, monkeypatch
):
    token = await _register(client, "ai-job-cancelled@example.com")
    account_id = await _create_account(client, token)

    create_response = await client.post(
        "/api/v1/settings/ai/profiles",
        json={
            "name": "Server locale",
            "provider": "custom",
            "endpoint": "http://fake-ai.local/v1",
            "model": "local-model",
        },
        headers=_auth_headers(token),
    )
    profile_id = create_response.json()["id"]
    await client.post(f"/api/v1/settings/ai/profiles/{profile_id}/activate", headers=_auth_headers(token))

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    user_id = me.json()["id"]
    await import_job(None, import_id, user_id)

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["ai_classification_status"] == "pending"

    async def _raise_cancelled(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(ai_classification_job, "classify_transaction", _raise_cancelled)

    raised = False
    try:
        await classify_import_transactions_job(None, import_id, user_id)
    except asyncio.CancelledError:
        raised = True
    assert raised, "una cancellazione reale non va mai assorbita silenziosamente"

    detail_after = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail_after.json()["ai_classification_status"] == "failed"

"""Job disaccoppiato di classificazione AI (rework "disaccoppiamento AI",
vedi worker/jobs/ai_classification_job.py) — copre lo stesso bug di
CancelledError-non-catturata gia' corretto in import_job.py: asyncio.
CancelledError eredita da BaseException (Python 3.8+), un `except
Exception:` la lascerebbe passare senza pulizia, lasciando l'import bloccato
per sempre in ai_classification_status='running'.
"""
import asyncio

import httpx
from httpx import AsyncClient

from app.worker.jobs import ai_classification_job
from app.worker.jobs.ai_classification_job import (
    _MAX_CONSECUTIVE_PROVIDER_ERRORS,
    classify_import_transactions_job,
)
from app.worker.jobs.import_job import import_job

# Merchant volutamente fittizio: deve restare NON classificabile da nessun
# livello deterministico della pipeline (regole/tipo/catalogo di sistema),
# altrimenti la riga non arriverebbe mai all'AI e questi test — che vogliono
# esercitare proprio il job AI — non testerebbero piu' nulla.
CSV_SAMPLE = "data,descrizione,importo\n2026-01-15,Pagamento ACME CORP SERVICE,-12.99\n"


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


async def test_provider_outage_stops_job_instead_of_faking_progress(client, httpx_mock):
    # Bug reale riportato dall'utente: un provider Ollama su un container
    # remoto spento a meta' import (per simulare un crash) non fermava il
    # job — ogni chiamata falliva silenziosamente ma il contatore "x/N
    # classificati" avanzava comunque, come se il provider rispondesse
    # normalmente. Qui si simula lo stesso scenario con un provider "custom"
    # e pytest-httpx che solleva ConnectError per ogni richiesta.
    token = await _register(client, "ai-job-outage@example.com")
    account_id = await _create_account(client, token)

    create_response = await client.post(
        "/api/v1/settings/ai/profiles",
        json={
            "name": "Provider irraggiungibile",
            "provider": "custom",
            "endpoint": "http://fake-ai-outage.local/v1",
            "model": "local-model",
        },
        headers=_auth_headers(token),
    )
    profile_id = create_response.json()["id"]
    await client.post(f"/api/v1/settings/ai/profiles/{profile_id}/activate", headers=_auth_headers(token))

    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url="http://fake-ai-outage.local/v1/chat/completions",
    )

    # Piu' righe di quante ne servano per superare la soglia di fallimenti
    # consecutivi, nessuna delle quali matcha una regola o il catalogo di
    # sistema (devono arrivare tutte all'AI).
    csv_rows = "\n".join(
        f"2026-01-{15 + i:02d},Pagamento generico presso terzi {i},-10.00" for i in range(_MAX_CONSECUTIVE_PROVIDER_ERRORS + 3)
    )
    csv_content = "data,descrizione,importo\n" + csv_rows + "\n"

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", csv_content.encode(), "text/csv")},
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
    await classify_import_transactions_job(None, import_id, user_id)

    detail = (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).json()
    assert detail["ai_classification_status"] == "failed"
    # Nessuna riga e' stata davvero classificata: il contatore non deve
    # avanzare fingendo progresso durante un'interruzione totale del
    # provider.
    assert detail["ai_transactions_classified"] == 0
    # Gap UX reale: l'utente deve poter sapere PERCHE' e' fallita, anche
    # dopo un refresh pagina (non solo via un evento SSE effimero).
    assert detail["ai_classification_error_message"] is not None
    assert "raggiungibile" in detail["ai_classification_error_message"]

    # Il job si e' fermato dopo la soglia di fallimenti consecutivi, non ha
    # scorso l'intera coda sapendo gia' che ogni chiamata sarebbe fallita.
    # Con la concorrenza (rework prompt AI, un provider "custom" usa
    # `ai_max_concurrency` richieste in volo, non 1 alla volta): il primo
    # batch intero viene inviato PRIMA che il conteggio dei fallimenti
    # consecutivi possa essere verificato riga per riga, quindi il numero
    # di richieste effettivamente inviate e' il batch che fa scattare la
    # soglia (qui l'intero primo batch, essendo piu' grande della soglia),
    # non esattamente `_MAX_CONSECUTIVE_PROVIDER_ERRORS`.
    from app.core.config import get_settings

    max_concurrency = get_settings().ai_max_concurrency
    requests = httpx_mock.get_requests(url="http://fake-ai-outage.local/v1/chat/completions")
    assert len(requests) == min(max_concurrency, _MAX_CONSECUTIVE_PROVIDER_ERRORS + 3)
    assert len(requests) >= _MAX_CONSECUTIVE_PROVIDER_ERRORS

    transactions = (
        await client.get(
            "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
        )
    ).json()
    assert all(t["category_id"] is None for t in transactions)

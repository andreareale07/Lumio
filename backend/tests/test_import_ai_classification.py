"""Integrazione worker import + AI (milestone 07, SPEC §28: Rules -> AI).
Stesso schema di test_classifications.py::test_import_classifies_matching_
transactions_via_rule, ma senza alcuna regola attiva: la riga Netflix viene
classificata dal provider "custom" (mockato via pytest-httpx, nessuna rete
reale), la riga Farmacia resta non classificata perche' il provider
risponde con `category_code: null`.
"""
import json

import httpx
from httpx import AsyncClient

from app.worker.jobs.import_job import import_job

CSV_SAMPLE = (
    "data,descrizione,importo\n"
    "2026-01-15,Pagamento NETFLIX.COM,-12.99\n"
    "2026-01-16,Farmacia Centrale,-8.00\n"
)


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


async def _category_id(client: AsyncClient, token: str, code: str) -> str:
    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    return next(c["id"] for c in response.json() if c["code"] == code)


def _custom_completion_callback(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    prompt = body["messages"][0]["content"]
    if "NETFLIX" in prompt:
        content = '{"category_code": "abbonamenti.streaming", "confidence": 0.92, "reason": "netflix"}'
    else:
        content = '{"category_code": null, "confidence": 0.2}'
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_import_classifies_unmatched_transaction_via_ai(client, httpx_mock):
    token = await _register(client, "ai-import@example.com")
    account_id = await _create_account(client, token)
    streaming_category_id = await _category_id(client, token, "abbonamenti.streaming")

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
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]
    activate_response = await client.post(
        f"/api/v1/settings/ai/profiles/{profile_id}/activate", headers=_auth_headers(token)
    )
    assert activate_response.status_code == 200

    httpx_mock.add_callback(
        _custom_completion_callback, url="http://fake-ai.local/v1/chat/completions"
    )

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    rows = transactions.json()
    netflix_row = next(r for r in rows if "NETFLIX" in r["description_raw"])
    pharmacy_row = next(r for r in rows if "Farmacia" in r["description_raw"])

    assert netflix_row["category_id"] == streaming_category_id
    assert pharmacy_row["category_id"] is None

    history = await client.get(
        f"/api/v1/transactions/{netflix_row['id']}/classifications", headers=_auth_headers(token)
    )
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["method"] == "ai"
    assert entries[0]["provider"] == "custom"
    assert entries[0]["model"] == "local-model"
    assert entries[0]["category_id"] == streaming_category_id
    # confidence 0.92 dichiarata, nessun merchant riconosciuto (nessun
    # parser lo popola ancora) -> discount fisso (app/services/confidence.py)
    assert entries[0]["score"] == "0.78"

    pharmacy_history = await client.get(
        f"/api/v1/transactions/{pharmacy_row['id']}/classifications", headers=_auth_headers(token)
    )
    assert pharmacy_history.json() == []


async def test_import_skips_ai_when_provider_is_none(client, httpx_mock):
    token = await _register(client, "ai-import-disabled@example.com")
    account_id = await _create_account(client, token)

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    # Nessuna richiesta HTTP verso alcun provider: httpx_mock solleverebbe
    # un errore se un test tentasse una richiesta non registrata, quindi
    # arrivare qui senza eccezioni conferma che l'AI (provider='none' di
    # default, SPEC §25) non e' mai stata invocata.
    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    rows = transactions.json()
    assert all(r["category_id"] is None for r in rows)

"""Endpoint SSE a livello HTTP: autorizzazione + replay (DoD a). Il
trasporto Redis Streams e' gia' testato in isolamento in test_job_events.py;
qui si verifica che l'endpoint lo esponga correttamente autenticato e
autorizzato per workspace.
"""
import json

from app.worker.jobs.import_csv import import_csv_job

CSV_SAMPLE = "data,descrizione,importo\n2026-01-15,Spesa,-10.00\n"


async def _register(client, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


def _parse_sse_events(raw_text: str) -> list[dict]:
    events = []
    for block in raw_text.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


async def test_events_endpoint_replays_events_emitted_before_job_ran(client):
    # DoD (a): il job puo' benissimo finire prima che qualunque client si
    # sia collegato allo stream — qui e' garantito, dato che lo si esegue
    # per intero PRIMA di aprire la connessione SSE.
    token = await _register(client, "events-replay@example.com")
    account_id = await _create_account(client, token)
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": upload.json()["preview"]["suggested_mapping"]},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_csv_job(None, import_id, me.json()["id"])

    async with client.stream(
        "GET", f"/api/v1/imports/{import_id}/events", headers=_auth_headers(token)
    ) as response:
        assert response.status_code == 200
        body = b""
        async for chunk in response.aiter_bytes():
            body += chunk
            if b"job.completed" in body:
                break

    events = _parse_sse_events(body.decode())
    assert [e["event"] for e in events] == ["job.created", "job.started", "job.progress", "job.progress", "job.completed"]


async def test_events_endpoint_requires_import_in_own_workspace(client):
    token_a = await _register(client, "events-cross-a@example.com")
    token_b = await _register(client, "events-cross-b@example.com")
    account_b = await _create_account(client, token_b)
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_b},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token_b),
    )
    import_b_id = upload.json()["import"]["id"]

    response = await client.get(
        f"/api/v1/imports/{import_b_id}/events", headers=_auth_headers(token_a)
    )
    assert response.status_code == 404

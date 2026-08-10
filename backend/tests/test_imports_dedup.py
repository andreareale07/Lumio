"""DoD (b) della milestone 04: upload dello stesso file due volte -> duplicato
rilevato, nessuna doppia transazione. Copre sia il check applicativo
"preventivo" sia — indirettamente, via test_rls_imports.py — la garanzia
reale a livello DB (indice unico parziale).
"""
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


async def _upload(client, token: str, account_id: str, content: bytes = CSV_SAMPLE.encode()):
    return await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", content, "text/csv")},
        headers=_auth_headers(token),
    )


async def test_second_upload_of_same_file_is_rejected(client):
    token = await _register(client, "dedup-a@example.com")
    account_id = await _create_account(client, token)

    first = await _upload(client, token, account_id)
    assert first.status_code == 201

    second = await _upload(client, token, account_id)
    assert second.status_code == 409
    assert second.json()["detail"]["existing_import_id"] == first.json()["import"]["id"]

    listing = await client.get("/api/v1/imports", headers=_auth_headers(token))
    assert len(listing.json()) == 1


async def test_reupload_allowed_after_cancel(client):
    token = await _register(client, "dedup-b@example.com")
    account_id = await _create_account(client, token)

    first = await _upload(client, token, account_id)
    import_id = first.json()["import"]["id"]
    await client.post(f"/api/v1/imports/{import_id}/cancel", headers=_auth_headers(token))

    second = await _upload(client, token, account_id)
    assert second.status_code == 201
    assert second.json()["import"]["id"] != import_id


async def test_reupload_allowed_after_worker_failure(client, monkeypatch):
    token = await _register(client, "dedup-c@example.com")
    account_id = await _create_account(client, token)

    upload = await _upload(client, token, account_id)
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )

    # Forza il job a fallire simulando un errore durante il parsing, per
    # verificare che lo stato 'failed' liberi davvero l'hash (indice unico
    # parziale — vedi test_rls_imports.py per la controparte a livello DB).
    def _boom(*args, **kwargs):
        raise RuntimeError("parsing esploso")

    monkeypatch.setattr("app.worker.jobs.import_csv.parse_rows", _boom)

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_csv_job(None, import_id, me.json()["id"])

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["status"] == "failed"

    second = await _upload(client, token, account_id)
    assert second.status_code == 201


async def test_dedup_is_scoped_per_workspace_not_global(client):
    token_a = await _register(client, "dedup-scope-a@example.com")
    token_b = await _register(client, "dedup-scope-b@example.com")
    account_a = await _create_account(client, token_a)
    account_b = await _create_account(client, token_b)

    response_a = await _upload(client, token_a, account_a)
    response_b = await _upload(client, token_b, account_b)

    assert response_a.status_code == 201
    assert response_b.status_code == 201

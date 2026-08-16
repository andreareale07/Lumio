from httpx import AsyncClient

_PAC_DESCRIPTION = (
    "Savings plan execution IE00B4L5Y983 iShares III plc - iShares Core MSCI "
    "World UCITS ETF USD (Acc), quantity: 1.194268"
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


async def test_preview_finds_a_would_change_row_without_writing_anything(client):
    token = await _register(client, "reclass-preview@example.com")
    account_id = await _create_account(client, token)

    create_response = await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id,
            "transaction_date": "2026-01-01",
            "description_raw": _PAC_DESCRIPTION,
            "amount": "-150.00",
            "currency": "EUR",
            "direction": "debit",
            "transaction_type": "investment",
        },
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    preview = await client.get(
        "/api/v1/classification/reclassify/preview",
        params={"scope": "uncategorized"},
        headers=_auth_headers(token),
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["would_change"] == 1
    assert any(b["category_code"] == "investimenti.versamento_pac" for b in body["breakdown"])

    # La preview e' un dry-run: nessuna scrittura, la transazione resta
    # esattamente come prima (nessuna categoria assegnata, nessuno storico).
    after = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))
    assert after.json()["category_id"] is None
    history = await client.get(
        f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
    )
    assert history.json() == []


async def test_preview_excludes_manually_classified_transactions(client):
    token = await _register(client, "reclass-preview-manual@example.com")
    account_id = await _create_account(client, token)
    categories = (await client.get("/api/v1/categories", headers=_auth_headers(token))).json()
    streaming = next(c for c in categories if c["code"] == "abbonamenti.streaming")

    await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id,
            "transaction_date": "2026-01-01",
            "description_raw": _PAC_DESCRIPTION,
            "amount": "-150.00",
            "currency": "EUR",
            "direction": "debit",
            "transaction_type": "investment",
            "category_id": streaming["id"],
        },
        headers=_auth_headers(token),
    )

    preview = await client.get(
        "/api/v1/classification/reclassify/preview",
        params={"scope": "all_except_manual"},
        headers=_auth_headers(token),
    )
    assert preview.status_code == 200
    # La transazione ha una classificazione 'manual': esclusa dal conteggio,
    # anche con scope='all_except_manual'.
    assert preview.json()["total_candidates"] == 0
    assert preview.json()["would_change"] == 0


async def test_trigger_reclassify_returns_202_and_job_id(client):
    token = await _register(client, "reclass-trigger@example.com")

    response = await client.post(
        "/api/v1/classification/reclassify",
        json={"scope": "uncategorized", "run_ai": False},
        headers=_auth_headers(token),
    )
    assert response.status_code == 202
    assert response.json()["job_id"]


async def test_trigger_reclassify_while_running_returns_same_job_without_double_enqueue(client):
    import uuid

    from app.db.rls import rls_session
    from app.models.job_run import JobRun
    from datetime import UTC, datetime

    token = await _register(client, "reclass-double-click@example.com")
    me = (await client.get("/api/v1/auth/me", headers=_auth_headers(token))).json()
    ws_probe = (await client.post(
        "/api/v1/categories", json={"name": "WS Probe", "code": "ws_probe_dc"}, headers=_auth_headers(token)
    )).json()
    workspace_id = uuid.UUID(ws_probe["workspace_id"])
    user_id = uuid.UUID(me["id"])

    # Simula un job gia' 'running' (come se un primo click lo avesse gia'
    # accodato pochi istanti prima).
    async with rls_session(user_id) as db:
        db.add(
            JobRun(
                workspace_id=workspace_id,
                job_kind="reclassification",
                status="running",
                job_id="fake-job-id-123",
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()

    response = await client.post(
        "/api/v1/classification/reclassify",
        json={"scope": "uncategorized", "run_ai": False},
        headers=_auth_headers(token),
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == "fake-job-id-123"


async def test_status_returns_null_when_never_run(client):
    token = await _register(client, "reclass-status-null@example.com")
    response = await client.get("/api/v1/classification/reclassify/status", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() is None


async def test_user_a_preview_never_sees_user_b_transactions(client):
    token_a = await _register(client, "reclass-isolation-a@example.com")
    token_b = await _register(client, "reclass-isolation-b@example.com")
    account_b = await _create_account(client, token_b)

    await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_b,
            "transaction_date": "2026-01-01",
            "description_raw": _PAC_DESCRIPTION,
            "amount": "-150.00",
            "currency": "EUR",
            "direction": "debit",
            "transaction_type": "investment",
        },
        headers=_auth_headers(token_b),
    )

    preview_a = await client.get(
        "/api/v1/classification/reclassify/preview",
        params={"scope": "uncategorized"},
        headers=_auth_headers(token_a),
    )
    assert preview_a.json()["total_candidates"] == 0

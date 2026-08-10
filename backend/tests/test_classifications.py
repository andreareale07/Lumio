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


def _transaction_payload(account_id: str, **overrides) -> dict:
    payload = {
        "financial_account_id": account_id,
        "transaction_date": "2026-08-01",
        "description_raw": "SUPERMERCATO LIDL MILANO",
        "amount": "-42.50",
        "currency": "EUR",
        "direction": "debit",
        "transaction_type": "expense",
    }
    payload.update(overrides)
    return payload


async def test_manual_creation_with_explicit_category_logs_manual_classification(client):
    token = await _register(client, "classif-manual@example.com")
    account_id = await _create_account(client, token)
    category_id = await _category_id(client, token, "alimentari.supermercato")

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, category_id=category_id),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    history = await client.get(
        f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
    )
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["method"] == "manual"
    assert entries[0]["category_id"] == category_id


async def test_manual_creation_without_category_leaves_no_classification_when_no_rule_matches(client):
    token = await _register(client, "classif-none@example.com")
    account_id = await _create_account(client, token)

    create_response = await client.post(
        "/api/v1/transactions", json=_transaction_payload(account_id), headers=_auth_headers(token)
    )
    transaction_id = create_response.json()["id"]
    assert create_response.json()["category_id"] is None

    history = await client.get(
        f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
    )
    assert history.json() == []


async def test_manual_creation_without_category_uses_matching_active_rule(client):
    token = await _register(client, "classif-rule-create@example.com")
    account_id = await _create_account(client, token)
    category_id = await _category_id(client, token, "abbonamenti.streaming")

    await client.post(
        "/api/v1/rules",
        json={
            "name": "Netflix",
            "field": "description",
            "operator": "contains",
            "value": "netflix",
            "category_id": category_id,
        },
        headers=_auth_headers(token),
    )

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, description_raw="Pagamento NETFLIX.COM"),
        headers=_auth_headers(token),
    )
    transaction = create_response.json()
    assert transaction["category_id"] == category_id

    history = await client.get(
        f"/api/v1/transactions/{transaction['id']}/classifications", headers=_auth_headers(token)
    )
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["method"] == "rule"
    assert entries[0]["category_id"] == category_id
    assert entries[0]["score"] == "1.00"


async def test_correcting_category_via_patch_logs_user_classification(client):
    token = await _register(client, "classif-correction@example.com")
    account_id = await _create_account(client, token)
    wrong_category = await _category_id(client, token, "tempo_libero.ristoranti")
    right_category = await _category_id(client, token, "alimentari.supermercato")

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, category_id=wrong_category),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    await client.patch(
        f"/api/v1/transactions/{transaction_id}",
        json={"category_id": right_category},
        headers=_auth_headers(token),
    )

    history = await client.get(
        f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
    )
    entries = history.json()
    assert [e["method"] for e in entries] == ["user", "manual"]
    assert entries[0]["category_id"] == right_category


async def test_patch_without_changing_category_does_not_add_classification(client):
    token = await _register(client, "classif-nochange@example.com")
    account_id = await _create_account(client, token)
    category_id = await _category_id(client, token, "alimentari.supermercato")

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, category_id=category_id),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    await client.patch(
        f"/api/v1/transactions/{transaction_id}",
        json={"category_id": category_id, "reference": "same category"},
        headers=_auth_headers(token),
    )

    history = await client.get(
        f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
    )
    assert len(history.json()) == 1


async def test_import_classifies_matching_transactions_via_rule(client):
    token = await _register(client, "classif-import@example.com")
    account_id = await _create_account(client, token)
    category_id = await _category_id(client, token, "abbonamenti.streaming")

    await client.post(
        "/api/v1/rules",
        json={
            "name": "Netflix",
            "field": "description",
            "operator": "contains",
            "value": "netflix",
            "category_id": category_id,
        },
        headers=_auth_headers(token),
    )

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    confirm = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])
    assert confirm.status_code == 200

    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    rows = transactions.json()
    netflix_row = next(r for r in rows if "NETFLIX" in r["description_raw"])
    pharmacy_row = next(r for r in rows if "Farmacia" in r["description_raw"])
    assert netflix_row["category_id"] == category_id
    assert pharmacy_row["category_id"] is None

    history = await client.get(
        f"/api/v1/transactions/{netflix_row['id']}/classifications", headers=_auth_headers(token)
    )
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["method"] == "rule"
    assert entries[0]["category_id"] == category_id

    pharmacy_history = await client.get(
        f"/api/v1/transactions/{pharmacy_row['id']}/classifications", headers=_auth_headers(token)
    )
    assert pharmacy_history.json() == []

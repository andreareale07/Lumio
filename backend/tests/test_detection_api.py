"""Test end-to-end (DB, `lumio_test`) degli endpoint di rilevazione
ricorrenze/anomalie (piano `synchronous-chasing-pike.md`, FETTA 2 §2.7-2.8)
— stesso stile di `test_analytics.py`."""
from datetime import date, timedelta

from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Conto", "account_type": "checking", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/accounts", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_transaction(client: AsyncClient, token: str, account_id: str, **overrides) -> dict:
    payload = {
        "financial_account_id": account_id,
        "transaction_date": "2026-01-01",
        "description_raw": "Movimento",
        "amount": "-10.00",
        "currency": "EUR",
        "direction": "debit",
        "transaction_type": "expense",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/transactions", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


def _monthly_dates(start: date, count: int) -> list[str]:
    dates = []
    y, m, d = start.year, start.month, start.day
    for i in range(count):
        month = (m - 1 + i) % 12 + 1
        year = y + (m - 1 + i) // 12
        dates.append(date(year, month, min(d, 28)).isoformat())
    return dates


async def _seed_monthly_expense_series(
    client: AsyncClient, token: str, account_id: str, *, months: int = 8, merchant: str = "Netflix"
) -> None:
    for d in _monthly_dates(date(2025, 1, 15), months):
        await _create_transaction(
            client,
            token,
            account_id,
            transaction_date=d,
            description_raw=f"PAGAMENTO POS {merchant.upper()}",
            merchant=merchant,
            amount="-12.99",
            direction="debit",
            transaction_type="expense",
        )


async def test_recurring_detects_monthly_subscription(client: AsyncClient):
    token = await _register(client, "recurring-monthly@example.com")
    account_id = await _create_account(client, token)
    await _seed_monthly_expense_series(client, token, account_id)

    response = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "as_of": "2026-01-25"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_data"] is False
    labels = [item["label"] for item in body["items"]]
    assert any("Netflix" in label for label in labels)
    netflix = next(item for item in body["items"] if "Netflix" in item["label"])
    assert netflix["cadence"] == "monthly"
    assert netflix["typical_amount"] == "12.99"


async def test_recurring_income_direction_returns_salary_not_expenses(client: AsyncClient):
    token = await _register(client, "recurring-income@example.com")
    account_id = await _create_account(client, token)
    await _seed_monthly_expense_series(client, token, account_id, merchant="Netflix")
    for d in _monthly_dates(date(2025, 1, 27), 8):
        await _create_transaction(
            client,
            token,
            account_id,
            transaction_date=d,
            description_raw="BONIFICO STIPENDIO",
            merchant="Datore Di Lavoro",
            amount="2000.00",
            direction="credit",
            transaction_type="income",
        )

    response = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "income", "as_of": "2026-01-25"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    labels = [item["label"] for item in body["items"]]
    assert any("Datore" in label for label in labels)
    assert all("Netflix" not in label for label in labels)


async def test_recurring_reports_unconverted_rows_when_no_fx_rate(client: AsyncClient):
    token = await _register(client, "recurring-fx@example.com")
    account_id = await _create_account(client, token, currency="USD")
    for d in _monthly_dates(date(2025, 1, 15), 6):
        await _create_transaction(
            client,
            token,
            account_id,
            transaction_date=d,
            description_raw="PAGAMENTO POS SPOTIFY",
            merchant="Spotify",
            amount="-9.99",
            currency="USD",
            direction="debit",
            transaction_type="expense",
        )

    response = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "currency": "EUR", "as_of": "2025-07-01"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    # Nessun tasso USD->EUR seedato in questo test: le righe restano
    # onestamente escluse dalle statistiche di importo (mai un'esclusione
    # invisibile), ma la cadenza resta valutabile sulla sola data.
    assert body["has_unconverted_rows"] is True


async def test_recurring_insufficient_data_with_short_history(client: AsyncClient):
    token = await _register(client, "recurring-short@example.com")
    account_id = await _create_account(client, token)
    await _create_transaction(
        client, token, account_id, transaction_date="2026-01-05", amount="-12.99", merchant="Netflix"
    )
    await _create_transaction(
        client, token, account_id, transaction_date="2026-01-20", amount="-12.99", merchant="Netflix"
    )

    response = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "as_of": "2026-01-25"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["insufficient_data"] is True


async def test_detection_override_dismiss_hides_and_undo_restores(client: AsyncClient):
    token = await _register(client, "override-dismiss@example.com")
    account_id = await _create_account(client, token)
    await _seed_monthly_expense_series(client, token, account_id)

    response = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "as_of": "2026-01-25"},
        headers=_auth_headers(token),
    )
    series_key = response.json()["items"][0]["series_key"]

    dismiss = await client.post(
        "/api/v1/analytics/detection-overrides",
        json={"override_type": "recurring_series", "series_key": series_key, "decision": "ignored"},
        headers=_auth_headers(token),
    )
    assert dismiss.status_code == 201
    override_id = dismiss.json()["id"]

    after_dismiss = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "as_of": "2026-01-25"},
        headers=_auth_headers(token),
    )
    assert all(item["series_key"] != series_key for item in after_dismiss.json()["items"])

    undo = await client.delete(
        f"/api/v1/analytics/detection-overrides/{override_id}", headers=_auth_headers(token)
    )
    assert undo.status_code == 204

    after_undo = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "as_of": "2026-01-25"},
        headers=_auth_headers(token),
    )
    assert any(item["series_key"] == series_key for item in after_undo.json()["items"])


async def test_detection_override_post_twice_is_idempotent(client: AsyncClient):
    token = await _register(client, "override-idempotent@example.com")
    account_id = await _create_account(client, token)
    await _seed_monthly_expense_series(client, token, account_id)

    response = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "as_of": "2026-01-25"},
        headers=_auth_headers(token),
    )
    series_key = response.json()["items"][0]["series_key"]

    first = await client.post(
        "/api/v1/analytics/detection-overrides",
        json={"override_type": "recurring_series", "series_key": series_key, "decision": "ignored"},
        headers=_auth_headers(token),
    )
    second = await client.post(
        "/api/v1/analytics/detection-overrides",
        json={"override_type": "recurring_series", "series_key": series_key, "decision": "ignored"},
        headers=_auth_headers(token),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_anomalies_flags_large_outlier_in_category(client: AsyncClient):
    token = await _register(client, "anomaly-outlier@example.com")
    account_id = await _create_account(client, token)
    category_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    groceries = next(c for c in category_response.json() if c["code"] == "alimentari")

    base = date(2025, 3, 1)
    for i in range(8):
        await _create_transaction(
            client,
            token,
            account_id,
            transaction_date=(base + timedelta(days=10 * i)).isoformat(),
            description_raw="Spesa",
            amount="-30.00",
            category_id=groceries["id"],
        )
    await _create_transaction(
        client,
        token,
        account_id,
        transaction_date="2026-01-15",
        description_raw="Spesa grande",
        amount="-350.00",
        category_id=groceries["id"],
    )

    response = await client.get(
        "/api/v1/analytics/anomalies",
        params={"direction": "expense", "date_from": "2026-01-01", "date_to": "2026-01-31"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert any(item["amount"] == "350.00" for item in body["items"])
    flagged = next(item for item in body["items"] if item["amount"] == "350.00")
    assert flagged["anomaly_type"] == "category_outlier"


async def test_workspace_isolation_recurring_series(client: AsyncClient):
    token_a = await _register(client, "isolation-a@example.com")
    account_a = await _create_account(client, token_a)
    await _seed_monthly_expense_series(client, token_a, account_a, merchant="OnlyA")

    token_b = await _register(client, "isolation-b@example.com")
    account_b = await _create_account(client, token_b)
    await _seed_monthly_expense_series(client, token_b, account_b, merchant="OnlyB")

    response_a = await client.get(
        "/api/v1/analytics/recurring",
        params={"direction": "expense", "as_of": "2026-01-25"},
        headers=_auth_headers(token_a),
    )
    labels_a = [item["label"] for item in response_a.json()["items"]]
    assert any("OnlyA" in label for label in labels_a)
    assert all("OnlyB" not in label for label in labels_a)

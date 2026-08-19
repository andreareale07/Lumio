"""Casi del saldo "ancora + delta" (SPEC §18: `financial_accounts` non ha
una colonna `balance`) esposto da `GET /analytics/balances`. Vedi
`app/services/analytics.py` per la query."""
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
    response = await client.post(
        "/api/v1/accounts", json=payload, headers=_auth_headers(token)
    )
    return response.json()["id"]


async def _create_transaction(client: AsyncClient, token: str, account_id: str, **overrides) -> dict:
    payload = {
        "financial_account_id": account_id,
        "transaction_date": "2026-08-01",
        "description_raw": "Movimento",
        "amount": "-10.00",
        "currency": "EUR",
        "direction": "debit",
        "transaction_type": "expense",
    }
    payload.update(overrides)
    response = await client.post(
        "/api/v1/transactions", json=payload, headers=_auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _balance_of(client: AsyncClient, token: str, account_id: str, **params) -> str:
    response = await client.get(
        "/api/v1/analytics/balances", params=params, headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    account = next(a for a in response.json()["accounts"] if a["financial_account_id"] == account_id)
    return account["balance"]


async def test_balance_falls_back_to_sum_when_no_balance_after(client):
    token = await _register(client, "balance-fallback@example.com")
    account_id = await _create_account(client, token)

    await _create_transaction(client, token, account_id, amount="500.00", direction="credit", transaction_type="income")
    await _create_transaction(client, token, account_id, amount="-120.00")

    assert await _balance_of(client, token, account_id) == "380.00"


async def test_balance_uses_anchor_plus_delta_when_present(client):
    token = await _register(client, "balance-anchor@example.com")
    account_id = await _create_account(client, token)

    # L'ancora (balance_after=1000.00) e' dichiarata dalla banca sull'estratto
    # importato; le transazioni successive senza balance_after (es. inserite
    # a mano) si somma al di sopra.
    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-01",
        amount="-50.00", balance_after="1000.00",
    )
    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-10",
        amount="200.00", direction="credit", transaction_type="income",
    )

    assert await _balance_of(client, token, account_id) == "1200.00"


async def test_balance_tie_break_on_same_day_uses_latest_created(client):
    token = await _register(client, "balance-tiebreak@example.com")
    account_id = await _create_account(client, token)

    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-01",
        amount="-50.00", balance_after="500.00",
    )
    # Stesso giorno, creata DOPO: deve diventare l'ancora (created_at/id
    # come tie-break), non la precedente.
    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-01",
        amount="10.00", direction="credit", transaction_type="income", balance_after="520.00",
    )

    assert await _balance_of(client, token, account_id) == "520.00"


async def test_balance_as_of_past_date_ignores_later_transactions(client):
    token = await _register(client, "balance-asof@example.com")
    account_id = await _create_account(client, token)

    await _create_transaction(
        client, token, account_id, transaction_date="2026-01-15", balance_after="100.00", amount="-5.00",
    )
    await _create_transaction(
        client, token, account_id, transaction_date="2026-02-15",
        amount="900.00", direction="credit", transaction_type="income",
    )

    assert await _balance_of(client, token, account_id) == "1000.00"
    assert await _balance_of(client, token, account_id, as_of="2026-01-20") == "100.00"


async def test_balances_without_fx_rate_excludes_and_flags_foreign_currency_account(client):
    # Nessun tasso USD->EUR persistito in questo test: il conto USD resta
    # onestamente escluso dal totale (nessun tasso disponibile), ma
    # `has_unconverted_rows` lo segnala — a differenza del vecchio
    # comportamento (esclusione muta, mai un flag).
    token = await _register(client, "balance-currency-no-rate@example.com")
    eur_account = await _create_account(client, token, name="EUR", currency="EUR")
    usd_account = await _create_account(client, token, name="USD", currency="USD")

    await _create_transaction(client, token, eur_account, amount="-10.00", currency="EUR")
    await _create_transaction(client, token, usd_account, amount="-9999.00", currency="USD")

    response = await client.get(
        "/api/v1/analytics/balances", params={"currency": "EUR"}, headers=_auth_headers(token)
    )
    body = response.json()
    account_ids = {a["financial_account_id"] for a in body["accounts"]}
    assert account_ids == {eur_account}
    assert body["has_unconverted_rows"] is True


async def test_balances_converts_foreign_currency_account_when_fx_rate_available(client):
    token = await _register(client, "balance-currency-with-rate@example.com")
    eur_account = await _create_account(client, token, name="EUR", currency="EUR")
    usd_account = await _create_account(client, token, name="USD", currency="USD")

    await _create_transaction(client, token, eur_account, amount="-10.00", currency="EUR")
    await _create_transaction(
        client, token, usd_account, amount="1000.00", currency="USD",
        direction="credit", transaction_type="income",
    )
    await client.put(
        "/api/v1/currencies/rates",
        json={"from_currency": "USD", "to_currency": "EUR", "rate_date": "2026-08-01", "rate": "0.90"},
        headers=_auth_headers(token),
    )

    response = await client.get(
        "/api/v1/analytics/balances",
        params={"currency": "EUR", "as_of": "2026-08-01"},
        headers=_auth_headers(token),
    )
    body = response.json()
    assert body["has_unconverted_rows"] is False
    account_ids = {a["financial_account_id"] for a in body["accounts"]}
    assert account_ids == {eur_account, usd_account}
    usd_balance = next(a for a in body["accounts"] if a["financial_account_id"] == usd_account)
    assert usd_balance["balance"] == "900.00"  # 1000 USD * 0.90
    # Il conto USD ora contribuisce al totale di liquidita', convertito.
    assert body["liquidity_total"] == "890.00"  # -10 EUR + 900 EUR

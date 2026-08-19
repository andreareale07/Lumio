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


async def _category_id(client: AsyncClient, token: str, code: str) -> str:
    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    return next(c["id"] for c in response.json() if c["code"] == code)


async def test_summary_excludes_transfers_and_investments(client):
    token = await _register(client, "summary@example.com")
    account_id = await _create_account(client, token)

    await _create_transaction(
        client, token, account_id,
        amount="2000.00", direction="credit", transaction_type="income",
    )
    await _create_transaction(
        client, token, account_id,
        amount="-500.00", direction="debit", transaction_type="expense",
    )
    await _create_transaction(
        client, token, account_id,
        amount="-300.00", direction="debit", transaction_type="transfer",
    )
    await _create_transaction(
        client, token, account_id,
        amount="-200.00", direction="debit", transaction_type="investment",
    )

    response = await client.get(
        "/api/v1/analytics/summary",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "EUR"
    # Cash flow ignora transfer/investment (SPEC §21/§30, CLAUDE.md).
    assert body["income"] == "2000.00"
    assert body["expenses"] == "500.00"
    assert body["net_cash_flow"] == "1500.00"
    # Il saldo del conto invece riflette TUTTE le transazioni reali,
    # transfer/investment incluse: 2000 - 500 - 300 - 200 = 1000.
    assert body["liquidity"] == "1000.00"
    assert body["has_investments"] is False
    # Rework dashboard interattivo: nuova KPI "Patrimonio totale" (SPEC.md
    # §39/§73) = liquidita' - debiti + investimenti, calcolata qui in
    # Decimal (non lato frontend in float). Nessun debito/investimento in
    # questo scenario -> coincide con la liquidita'.
    assert body["net_worth"] == "1000.00"


async def test_brokerage_account_counts_as_liquidity_not_investment(client):
    # Decisione rivista dopo feedback reale: conti come Trade Republic/
    # Fineco sono ibridi (spendibili con carta E utilizzabili per comprare
    # titoli sullo stesso conto) — "brokerage" non deve escludere il saldo
    # dalla liquidita'. Nessun account_type oggi da' diritto a un valore di
    # investimento reale (arriva con M09), quindi has_investments resta
    # sempre False.
    token = await _register(client, "brokerage-liquidity@example.com")
    brokerage_id = await _create_account(client, token, account_type="brokerage")
    credit_card_id = await _create_account(client, token, account_type="credit_card")

    await _create_transaction(
        client, token, brokerage_id, amount="872.70", direction="credit", transaction_type="income"
    )
    await _create_transaction(client, token, credit_card_id, amount="-50.00")

    response = await client.get("/api/v1/analytics/balances", headers=_auth_headers(token))
    body = response.json()
    assert body["liquidity_total"] == "872.70"
    assert body["debt_total"] == "-50.00"
    assert body["investment_total"] == "0.00"
    assert body["has_investments"] is False


async def test_net_worth_subtracts_debt_not_adds_it(client):
    # Bug reale (rework dashboard interattivo): `debt_total` e' GIA' un
    # saldo con segno (negativo quando si e' in debito, vedi il test sopra)
    # — la prima versione di questa formula lo SOTTRAEVA di nuovo
    # (liquidity - debt), raddoppiando l'effetto e restituendo un
    # patrimonio PIU' alto in presenza di debiti invece che piu' basso.
    # Speculare a `_upsert_net_worth_snapshot` in portfolio_analytics.py,
    # che soffriva dello stesso rischio se scritta cosi'.
    token = await _register(client, "net-worth-debt@example.com")
    checking_id = await _create_account(client, token, account_type="checking")
    credit_card_id = await _create_account(client, token, account_type="credit_card")

    await _create_transaction(
        client, token, checking_id, amount="3000.00", direction="credit", transaction_type="income"
    )
    await _create_transaction(client, token, credit_card_id, amount="-450.00")

    response = await client.get(
        "/api/v1/analytics/summary",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31"},
        headers=_auth_headers(token),
    )
    body = response.json()
    assert body["liquidity"] == "3000.00"
    assert body["debt"] == "-450.00"
    assert body["net_worth"] == "2550.00"


async def test_by_category_rolls_up_subcategories_to_parent(client):
    token = await _register(client, "category@example.com")
    account_id = await _create_account(client, token)
    supermercato_id = await _category_id(client, token, "alimentari.supermercato")
    mercato_id = await _category_id(client, token, "alimentari.mercato")

    await _create_transaction(
        client, token, account_id, category_id=supermercato_id, amount="-100.00"
    )
    await _create_transaction(
        client, token, account_id, category_id=mercato_id, amount="-50.00"
    )

    response = await client.get(
        "/api/v1/analytics/by-category",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31", "direction": "expense"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Alimentari"
    assert items[0]["total"] == "150.00"
    assert items[0]["transactions_count"] == 2
    assert items[0]["share"] == "1"


async def test_by_merchant_breakdown_and_category_drilldown(client):
    token = await _register(client, "merchant@example.com")
    account_id = await _create_account(client, token)
    supermercato_id = await _category_id(client, token, "alimentari.supermercato")

    await _create_transaction(
        client, token, account_id, merchant="LIDL", category_id=supermercato_id, amount="-30.00"
    )
    await _create_transaction(
        client, token, account_id, merchant="ESSELUNGA", category_id=supermercato_id, amount="-20.00"
    )
    await _create_transaction(
        client, token, account_id, merchant="NETFLIX", amount="-9.99"
    )

    all_merchants = await client.get(
        "/api/v1/analytics/by-merchant",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31", "direction": "expense"},
        headers=_auth_headers(token),
    )
    assert {i["merchant"] for i in all_merchants.json()["items"]} == {"LIDL", "ESSELUNGA", "NETFLIX"}

    drilldown = await client.get(
        "/api/v1/analytics/by-merchant",
        params={
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
            "direction": "expense",
            "category_id": supermercato_id,
        },
        headers=_auth_headers(token),
    )
    assert {i["merchant"] for i in drilldown.json()["items"]} == {"LIDL", "ESSELUNGA"}


async def test_by_merchant_drilldown_on_parent_category_includes_subcategory_transactions(client):
    # Bug osservato manualmente in browser: il frontend passa a
    # /by-merchant?category_id=... il group_id RIACCORPATO di /by-category
    # (COALESCE(parent_id, id) — quasi sempre il padre), ma le transazioni
    # sono taggate con la SOTTOCATEGORIA figlia. Un confronto diretto
    # category_id == :category_id non trova mai nulla per un padre con
    # figli.
    token = await _register(client, "merchant-parent-drilldown@example.com")
    account_id = await _create_account(client, token)
    alimentari_id = await _category_id(client, token, "alimentari")
    supermercato_id = await _category_id(client, token, "alimentari.supermercato")
    assert alimentari_id != supermercato_id

    await _create_transaction(
        client, token, account_id, merchant="LIDL", category_id=supermercato_id, amount="-30.00"
    )

    drilldown = await client.get(
        "/api/v1/analytics/by-merchant",
        params={
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
            "direction": "expense",
            "category_id": alimentari_id,
        },
        headers=_auth_headers(token),
    )
    items = drilldown.json()["items"]
    assert items
    assert {i["merchant"] for i in items} == {"LIDL"}


async def test_cash_flow_buckets_by_month(client):
    token = await _register(client, "cashflow@example.com")
    account_id = await _create_account(client, token)

    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-15",
        amount="1000.00", direction="credit", transaction_type="income",
    )
    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-20", amount="-200.00",
    )
    await _create_transaction(
        client, token, account_id, transaction_date="2026-09-10",
        amount="500.00", direction="credit", transaction_type="income",
    )

    response = await client.get(
        "/api/v1/analytics/cash-flow",
        params={"date_from": "2026-08-01", "date_to": "2026-09-30", "granularity": "month"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    points = {p["period"]: p for p in response.json()["points"]}
    assert points["2026-08-01"]["income"] == "1000.00"
    assert points["2026-08-01"]["expenses"] == "200.00"
    assert points["2026-08-01"]["net"] == "800.00"
    assert points["2026-09-01"]["income"] == "500.00"
    # Sistema di valute: ora sempre quantizzato a 2 decimali (prima "0" per
    # un dettaglio incidentale del tipo NUMERIC restituito da Postgres,
    # senza la moltiplicazione per il tasso di cambio) — formattazione piu'
    # coerente, non piu' dipendente da quale ramo SQL ha prodotto lo zero.
    assert points["2026-09-01"]["expenses"] == "0.00"


async def test_cash_flow_buckets_by_semester(client):
    # Rework UX/design slice 1: Postgres non ha date_trunc('semester', ...)
    # nativo (app/services/analytics.py:_bucket_expr costruisce un CASE a
    # mano) — verifica end-to-end che il bucketing SQL combaci con
    # generate_buckets lato Python (test_analytics_calc.py).
    token = await _register(client, "cashflow-semester@example.com")
    account_id = await _create_account(client, token)

    await _create_transaction(
        client, token, account_id, transaction_date="2026-02-10",
        amount="1000.00", direction="credit", transaction_type="income",
    )
    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-15",
        amount="300.00", direction="credit", transaction_type="income",
    )

    response = await client.get(
        "/api/v1/analytics/cash-flow",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31", "granularity": "semester"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    points = {p["period"]: p for p in response.json()["points"]}
    assert set(points) == {"2026-01-01", "2026-07-01"}
    assert points["2026-01-01"]["income"] == "1000.00"
    assert points["2026-07-01"]["income"] == "300.00"


async def test_cash_flow_filters_by_category_matching_parent_or_child(client):
    # Drill-down del cruscotto (rework dashboard interattivo): il trend di
    # una categoria deve trovare le transazioni sulla categoria stessa E su
    # una sua sottocategoria, stesso pattern gia' verificato per by_merchant.
    token = await _register(client, "cashflow-category@example.com")
    account_id = await _create_account(client, token)
    alimentari = await _category_id(client, token, "alimentari")
    supermercato = await _category_id(client, token, "alimentari.supermercato")
    trasporti = await _category_id(client, token, "trasporti")

    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-15",
        amount="-50.00", category_id=supermercato,
    )
    await _create_transaction(
        client, token, account_id, transaction_date="2026-08-16",
        amount="-30.00", category_id=trasporti,
    )

    response = await client.get(
        "/api/v1/analytics/cash-flow",
        params={
            "date_from": "2026-08-01", "date_to": "2026-08-31", "granularity": "month",
            "category_id": alimentari,
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    points = response.json()["points"]
    assert points[0]["expenses"] == "50.00"


async def test_invalid_granularity_returns_400(client):
    token = await _register(client, "invalid-granularity@example.com")

    response = await client.get(
        "/api/v1/analytics/cash-flow",
        params={"granularity": "decade"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


async def test_balance_history_last_point_matches_current_liquidity(client):
    token = await _register(client, "history@example.com")
    account_id = await _create_account(client, token)

    await _create_transaction(client, token, account_id, transaction_date="2026-07-10", amount="1000.00", direction="credit", transaction_type="income")
    await _create_transaction(client, token, account_id, transaction_date="2026-08-05", amount="-150.00")

    balances = await client.get("/api/v1/analytics/balances", headers=_auth_headers(token))
    history = await client.get(
        "/api/v1/analytics/balance-history",
        params={"date_from": "2026-07-01", "date_to": "2026-08-31", "granularity": "month"},
        headers=_auth_headers(token),
    )
    assert history.status_code == 200
    points = history.json()["points"]
    assert points[-1]["balance"] == balances.json()["liquidity_total"]


async def test_analytics_do_not_leak_across_workspaces(client):
    token_a = await _register(client, "iso-a@example.com")
    token_b = await _register(client, "iso-b@example.com")
    account_a = await _create_account(client, token_a)
    account_b = await _create_account(client, token_b)

    await _create_transaction(client, token_a, account_a, amount="-40.00")
    await _create_transaction(
        client, token_b, account_b, amount="-9000.00", merchant="SHOULD-NOT-LEAK"
    )

    summary_a = await client.get(
        "/api/v1/analytics/summary",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31"},
        headers=_auth_headers(token_a),
    )
    assert summary_a.json()["expenses"] == "40.00"

    by_merchant_a = await client.get(
        "/api/v1/analytics/by-merchant",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31", "direction": "expense"},
        headers=_auth_headers(token_a),
    )
    assert "SHOULD-NOT-LEAK" not in {i["merchant"] for i in by_merchant_a.json()["items"]}


# --- Sistema di valute: conversione invece di esclusione -------------------


async def test_cash_flow_converts_foreign_currency_transaction(client):
    token = await _register(client, "cashflow-fx@example.com")
    account_id = await _create_account(client, token, currency="USD")
    await _create_transaction(
        client, token, account_id, currency="USD",
        amount="1000.00", direction="credit", transaction_type="income",
    )
    await client.put(
        "/api/v1/currencies/rates",
        json={"from_currency": "USD", "to_currency": "EUR", "rate_date": "2026-08-01", "rate": "0.90"},
        headers=_auth_headers(token),
    )

    response = await client.get(
        "/api/v1/analytics/cash-flow",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31", "granularity": "month", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    points = response.json()["points"]
    assert points[0]["income"] == "900.00"  # 1000 USD * 0.90


async def test_by_category_converts_foreign_currency_transaction(client):
    token = await _register(client, "by-category-fx@example.com")
    account_id = await _create_account(client, token, currency="USD")
    supermercato_id = await _category_id(client, token, "alimentari.supermercato")
    await _create_transaction(
        client, token, account_id, currency="USD", category_id=supermercato_id, amount="-100.00",
    )
    await client.put(
        "/api/v1/currencies/rates",
        json={"from_currency": "USD", "to_currency": "EUR", "rate_date": "2026-08-01", "rate": "0.90"},
        headers=_auth_headers(token),
    )

    response = await client.get(
        "/api/v1/analytics/by-category",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31", "direction": "expense", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["total"] == "90.00"  # 100 USD * 0.90


async def test_resolve_currency_uses_workspace_base_currency_not_account_heuristic(client):
    """Regressione: prima la valuta di default era quella con piu' conti nel
    workspace (euristica automatica, avrebbe scelto USD qui sotto) — ora e'
    sempre `Workspace.base_currency` (default 'EUR' per un workspace nuovo),
    indipendentemente da quanti conti esistono in un'altra valuta.

    Nota: cambiare `base_currency` via API (Step D, `PATCH /workspace`) non
    e' ancora testabile qui — scrivendo questo test e' emerso che
    `workspaces` non ha ancora NESSUNA policy RLS di UPDATE (solo SELECT/
    INSERT, migration 0002): lo Step D dovra' aggiungerla."""
    token = await _register(client, "resolve-currency-base@example.com")

    # Due conti USD contro uno EUR: l'euristica precedente avrebbe risolto
    # a USD, non piu' rilevante ora.
    await _create_account(client, token, name="USD 1", currency="USD")
    await _create_account(client, token, name="USD 2", currency="USD")
    await _create_account(client, token, name="EUR", currency="EUR")

    response = await client.get(
        "/api/v1/analytics/summary",
        params={"date_from": "2026-08-01", "date_to": "2026-08-31"},
        headers=_auth_headers(token),
    )
    assert response.json()["currency"] == "EUR"

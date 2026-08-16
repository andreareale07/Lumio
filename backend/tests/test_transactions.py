from httpx import AsyncClient


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


async def test_create_and_list_transaction(client):
    token = await _register(client, "tx-owner@example.com")
    account_id = await _create_account(client, token)

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    transaction = create_response.json()
    assert transaction["description_raw"] == "SUPERMERCATO LIDL MILANO"
    assert transaction["amount"] == "-42.50"

    list_response = await client.get("/api/v1/transactions", headers=_auth_headers(token))
    assert list_response.status_code == 200
    assert [t["id"] for t in list_response.json()] == [transaction["id"]]


async def test_create_transaction_rejects_foreign_account(client):
    token_a = await _register(client, "tx-cross-a@example.com")
    token_b = await _register(client, "tx-cross-b@example.com")
    account_b_id = await _create_account(client, token_b)

    response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_b_id),
        headers=_auth_headers(token_a),
    )
    assert response.status_code == 400


async def test_update_transaction_category(client):
    token = await _register(client, "tx-editor@example.com")
    account_id = await _create_account(client, token)
    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    categories_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    supermarket_category = next(
        c for c in categories_response.json() if c["code"] == "alimentari.supermercato"
    )

    update_response = await client.patch(
        f"/api/v1/transactions/{transaction_id}",
        json={"category_id": supermarket_category["id"]},
        headers=_auth_headers(token),
    )
    assert update_response.status_code == 200
    assert update_response.json()["category_id"] == supermarket_category["id"]


async def test_manual_category_at_creation_never_needs_review(client):
    token = await _register(client, "tx-manual-create@example.com")
    account_id = await _create_account(client, token)
    categories_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    supermarket_category = next(
        c for c in categories_response.json() if c["code"] == "alimentari.supermercato"
    )

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, category_id=supermarket_category["id"]),
        headers=_auth_headers(token),
    )
    assert create_response.json()["needs_review"] is False


async def test_manual_correction_clears_needs_review(client):
    import uuid

    from app.db.rls import rls_session
    from app.models.transaction import Transaction

    token = await _register(client, "tx-manual-correction@example.com")
    account_id = await _create_account(client, token)
    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]
    assert create_response.json()["needs_review"] is False

    # Simula l'esito di una classificazione AI a bassa confidence (mai
    # possibile da produrre in un solo giro via API senza un provider AI
    # vero): scrittura diretta, come farebbe la pipeline.
    me = (await client.get("/api/v1/auth/me", headers=_auth_headers(token))).json()
    async with rls_session(uuid.UUID(me["id"])) as db:
        txn = await db.get(Transaction, uuid.UUID(transaction_id))
        txn.needs_review = True
        await db.commit()

    categories_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    supermarket_category = next(
        c for c in categories_response.json() if c["code"] == "alimentari.supermercato"
    )
    update_response = await client.patch(
        f"/api/v1/transactions/{transaction_id}",
        json={"category_id": supermarket_category["id"]},
        headers=_auth_headers(token),
    )
    assert update_response.json()["needs_review"] is False


async def test_review_summary_counts_uncategorized_and_needs_review_as_pending(client):
    import uuid

    from app.db.rls import rls_session
    from app.models.transaction import Transaction

    token = await _register(client, "tx-review-summary@example.com")
    account_id = await _create_account(client, token)
    categories_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    supermarket_category = next(
        c for c in categories_response.json() if c["code"] == "alimentari.supermercato"
    )

    # Risolta: categorizzata manualmente, mai da verificare.
    resolved = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, category_id=supermarket_category["id"]),
        headers=_auth_headers(token),
    )
    # Mai classificata: nessuna categoria.
    unclassified = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    # Classificata ma incerta: simula l'esito di un'AI a bassa confidence.
    uncertain = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, category_id=supermarket_category["id"]),
        headers=_auth_headers(token),
    )
    me = (await client.get("/api/v1/auth/me", headers=_auth_headers(token))).json()
    async with rls_session(uuid.UUID(me["id"])) as db:
        txn = await db.get(Transaction, uuid.UUID(uncertain.json()["id"]))
        txn.needs_review = True
        await db.commit()

    summary = await client.get("/api/v1/transactions/review-summary", headers=_auth_headers(token))
    assert summary.status_code == 200
    body = summary.json()
    assert body["total"] == 3
    assert body["classified"] == 1
    assert body["needs_review"] == 2
    assert resolved.json()["needs_review"] is False

    # Bug reale: il filtro della lista deve trovare ESATTAMENTE le righe
    # contate come "da verificare" dal riepilogo — comprese quelle mai
    # classificate (category_id NULL, needs_review ancora false di
    # default), non solo quelle con needs_review=true. Prima del fix,
    # un import con solo righe "mai classificate" mostrava un badge > 0
    # ma un elenco filtrato sempre vuoto.
    pending_list = await client.get(
        "/api/v1/transactions", params={"needs_review": "true"}, headers=_auth_headers(token)
    )
    assert {t["id"] for t in pending_list.json()} == {uncertain.json()["id"], unclassified.json()["id"]}


async def test_user_a_cannot_see_user_b_transaction_via_api(client):
    token_a = await _register(client, "tx-a@example.com")
    token_b = await _register(client, "tx-b@example.com")
    account_b_id = await _create_account(client, token_b)

    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_b_id),
        headers=_auth_headers(token_b),
    )
    transaction_b_id = create_response.json()["id"]

    get_response = await client.get(
        f"/api/v1/transactions/{transaction_b_id}", headers=_auth_headers(token_a)
    )
    assert get_response.status_code == 404

    list_response = await client.get("/api/v1/transactions", headers=_auth_headers(token_a))
    assert list_response.json() == []


async def test_delete_transaction(client):
    token = await _register(client, "tx-deleter@example.com")
    account_id = await _create_account(client, token)
    create_response = await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id),
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token)
    )
    assert get_response.status_code == 404


async def test_list_transactions_by_category_id_matches_parent_or_child(client):
    # Bug noto (gia' risolto in analytics.by_merchant, qui replicato): un
    # link "vedi le transazioni di Trasporti" con l'id della categoria
    # PADRE deve trovare le transazioni taggate con la sua SOTTOCATEGORIA,
    # non restituire una lista vuota per un match esatto che non puo' mai
    # avvenire (le transazioni sono sempre taggate a livello di foglia).
    token = await _register(client, "tx-category-parent-child@example.com")
    account_id = await _create_account(client, token)

    categories = await client.get("/api/v1/categories", headers=_auth_headers(token))
    trasporti = next(c for c in categories.json() if c["code"] == "trasporti")
    carburante = next(c for c in categories.json() if c["code"] == "trasporti.carburante")

    await client.post(
        "/api/v1/transactions",
        json=_transaction_payload(account_id, category_id=carburante["id"]),
        headers=_auth_headers(token),
    )

    by_child = await client.get(
        "/api/v1/transactions",
        params={"financial_account_id": account_id, "category_id": carburante["id"]},
        headers=_auth_headers(token),
    )
    assert len(by_child.json()) == 1

    by_parent = await client.get(
        "/api/v1/transactions",
        params={"financial_account_id": account_id, "category_id": trasporti["id"]},
        headers=_auth_headers(token),
    )
    assert len(by_parent.json()) == 1
    assert by_parent.json()[0]["category_id"] == carburante["id"]

"""Job di riclassificazione (rework tassonomia/pipeline): le invarianti
centrali sono che una correzione manuale non venga MAI toccata e che il job
non azzeri mai una categoria esistente se la pipeline non trova nulla.
"""
from httpx import AsyncClient

from app.worker.jobs.reclassification_job import reclassify_workspace_job

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


async def _category_by_code(client: AsyncClient, token: str, code: str) -> dict:
    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    return next(c for c in response.json() if c["code"] == code)


async def _run_job(client: AsyncClient, token: str, *, scope: str = "all_except_manual", run_ai: bool = False) -> None:
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = (await client.post(
        "/api/v1/categories", json={"name": "WS Probe", "code": f"probe_{me.json()['id'][:8]}"},
        headers=_auth_headers(token),
    )).json()["workspace_id"]
    await reclassify_workspace_job(None, workspace_id, me.json()["id"], scope, run_ai)


async def test_manual_classification_is_never_touched(client):
    token = await _register(client, "reclass-manual@example.com")
    account_id = await _create_account(client, token)
    wrong_category = await _category_by_code(client, token, "abbonamenti.streaming")

    # Un utente assegna DELIBERATAMENTE una categoria "sbagliata" (rispetto
    # a cio' che la pipeline dedurrebbe da transaction_type=investment) a
    # una transazione PAC — deve restare cosi' anche dopo la
    # riclassificazione, perche' e' una scelta esplicita dell'utente
    # (method='manual', assegnata in creazione).
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
            "category_id": wrong_category["id"],
        },
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    transaction_id = create_response.json()["id"]

    await _run_job(client, token, scope="all_except_manual", run_ai=False)

    after = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))
    assert after.json()["category_id"] == wrong_category["id"]

    history = await client.get(
        f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
    )
    # Nessuna nuova riga di classificazione: il job non ha nemmeno tentato
    # di valutare questa transazione (esclusa gia' dalla query di eleggibilita').
    assert len(history.json()) == 1
    assert history.json()[0]["method"] == "manual"


async def test_incorrect_ai_classification_gets_corrected(client):
    token = await _register(client, "reclass-fix-ai@example.com")
    account_id = await _create_account(client, token)
    wrong_category = await _category_by_code(client, token, "abbonamenti.streaming")
    correct_category = await _category_by_code(client, token, "investimenti.versamento_pac")

    # Scenario reale riportato dall'utente: un PAC su ETF classificato
    # dall'AI (prima del rework) come "Abbonamenti/Streaming".
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
    # Nessuna regola/categoria nel payload => la transazione resta NULL alla
    # creazione (nessuna regola matcha); simuliamo qui il risultato di una
    # vecchia classificazione AI sbagliata via PATCH... ma PATCH logga
    # method='user'. Per simulare esattamente un metodo='ai' pregresso,
    # inseriamo la Classification/il category_id direttamente via SQL.
    from app.db.rls import rls_session
    from app.models.classification import Classification
    from app.models.transaction import Transaction
    import uuid

    me = (await client.get("/api/v1/auth/me", headers=_auth_headers(token))).json()
    async with rls_session(uuid.UUID(me["id"])) as db:
        txn = await db.get(Transaction, uuid.UUID(transaction_id))
        txn.category_id = uuid.UUID(wrong_category["id"])
        db.add(
            Classification(
                transaction_id=txn.id,
                method="ai",
                provider="custom",
                model="local-model",
                category_id=uuid.UUID(wrong_category["id"]),
                score=0.6,
                explanation="ipotesi errata pre-rework",
            )
        )
        await db.commit()

    await _run_job(client, token, scope="all_except_manual", run_ai=False)

    after = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))
    assert after.json()["category_id"] == correct_category["id"]

    history = (
        await client.get(
            f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
        )
    ).json()
    # La vecchia riga 'ai' resta (append-only, mai cancellata), una nuova
    # riga 'system' si aggiunge.
    assert len(history) == 2
    methods = {entry["method"] for entry in history}
    assert methods == {"ai", "system"}


async def test_pipeline_returning_none_does_not_clear_existing_category(client):
    token = await _register(client, "reclass-no-clear@example.com")
    account_id = await _create_account(client, token)
    existing_category = await _category_by_code(client, token, "shopping.regali")

    create_response = await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id,
            "transaction_date": "2026-01-01",
            "description_raw": "Pagamento ACME COMPLETAMENTE GENERICO SRL",
            "amount": "-30.00",
            "currency": "EUR",
            "direction": "debit",
            "transaction_type": "expense",
        },
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]

    from app.db.rls import rls_session
    from app.models.classification import Classification
    from app.models.transaction import Transaction
    import uuid

    me = (await client.get("/api/v1/auth/me", headers=_auth_headers(token))).json()
    async with rls_session(uuid.UUID(me["id"])) as db:
        txn = await db.get(Transaction, uuid.UUID(transaction_id))
        txn.category_id = uuid.UUID(existing_category["id"])
        db.add(
            Classification(
                transaction_id=txn.id, method="ai", provider="custom", model="local-model",
                category_id=uuid.UUID(existing_category["id"]), score=0.5,
            )
        )
        await db.commit()

    await _run_job(client, token, scope="all_except_manual", run_ai=False)

    after = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))
    # Nessun livello deterministico trova nulla per una descrizione cosi'
    # generica: la categoria esistente NON viene azzerata.
    assert after.json()["category_id"] == existing_category["id"]


async def test_uncategorized_scope_only_touches_null_category_rows(client):
    token = await _register(client, "reclass-scope-uncategorized@example.com")
    account_id = await _create_account(client, token)
    wrong_category = await _category_by_code(client, token, "abbonamenti.streaming")

    already_categorized = await client.post(
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
    transaction_id = already_categorized.json()["id"]

    from app.db.rls import rls_session
    from app.models.classification import Classification
    from app.models.transaction import Transaction
    import uuid

    me = (await client.get("/api/v1/auth/me", headers=_auth_headers(token))).json()
    async with rls_session(uuid.UUID(me["id"])) as db:
        txn = await db.get(Transaction, uuid.UUID(transaction_id))
        txn.category_id = uuid.UUID(wrong_category["id"])
        db.add(
            Classification(
                transaction_id=txn.id, method="ai", provider="custom", model="local-model",
                category_id=uuid.UUID(wrong_category["id"]), score=0.5,
            )
        )
        await db.commit()

    # scope='uncategorized': la transazione ha gia' una categoria (sbagliata,
    # ma NON manuale) -> non e' eleggibile con questo scope, resta com'e'.
    await _run_job(client, token, scope="uncategorized", run_ai=False)

    after = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))
    assert after.json()["category_id"] == wrong_category["id"]


async def test_merchant_backfill_applies_even_to_manually_classified_rows(client):
    token = await _register(client, "reclass-merchant-backfill@example.com")
    account_id = await _create_account(client, token)
    category = await _category_by_code(client, token, "alimentari.supermercato")

    create_response = await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id,
            "transaction_date": "2026-01-01",
            "description_raw": "PAGAMENTO POS LIDL ITALIA SRL MILANO",
            "amount": "-42.50",
            "currency": "EUR",
            "direction": "debit",
            "transaction_type": "expense",
            "category_id": category["id"],
        },
        headers=_auth_headers(token),
    )
    transaction_id = create_response.json()["id"]
    assert create_response.json()["merchant"] is None  # nessun merchant al momento della creazione manuale

    await _run_job(client, token, scope="all_except_manual", run_ai=False)

    after = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))
    # Il merchant e' un arricchimento puro: si applica anche a una riga
    # protetta dalla riclassificazione della CATEGORIA.
    assert after.json()["merchant"] == "Lidl"
    assert after.json()["category_id"] == category["id"]  # categoria manuale invariata


async def test_second_run_is_idempotent(client):
    token = await _register(client, "reclass-idempotent@example.com")
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

    await _run_job(client, token, scope="all_except_manual", run_ai=False)
    first = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))

    await _run_job(client, token, scope="all_except_manual", run_ai=False)
    second = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth_headers(token))

    assert first.json()["category_id"] == second.json()["category_id"]

    history = (
        await client.get(
            f"/api/v1/transactions/{transaction_id}/classifications", headers=_auth_headers(token)
        )
    ).json()
    # La seconda esecuzione non ha aggiunto una seconda riga 'system'
    # identica: la categoria non e' cambiata rispetto a quella gia'
    # assegnata dalla prima esecuzione (nessuna nuova scrittura).
    assert len(history) == 1

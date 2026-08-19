"""Transaction Deduplication Engine — test end-to-end della pipeline
(upload -> confirm -> job -> eventuale review -> decisione), attraverso le
API reali. Complementa test_transaction_dedup_engine.py (algoritmo puro) e
test_rls_transaction_dedup.py (isolamento multi-tenant a livello DB).

Pattern "via API" (stesso di test_imports_dedup.py): il job viene invocato
direttamente (`await import_job(None, import_id, user_id)`), bypassando
Redis/arq — stessa tecnica gia' in uso nella suite esistente.
"""
from decimal import Decimal

from app.worker.jobs.import_job import import_job

CSV_HEADER = "data,descrizione,importo\n"


async def _register(client, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _user_id(client, token: str) -> str:
    response = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    return response.json()["id"]


async def _create_account(client, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def _upload_and_confirm(client, token: str, account_id: str, csv_body: str) -> str:
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", (CSV_HEADER + csv_body).encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    assert upload.status_code == 201, upload.text
    body = upload.json()
    import_id = body["import"]["id"]
    confirm = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": body["preview"]["suggested_mapping"]},
        headers=_auth_headers(token),
    )
    assert confirm.status_code == 200, confirm.text
    return import_id


async def _run_job(client, token: str, import_id: str) -> dict:
    user_id = await _user_id(client, token)
    await import_job(None, import_id, user_id)
    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.status_code == 200
    return detail.json()


async def test_overlapping_imports_produce_no_duplicate_transactions(client):
    """SPEC Test 2: PDF/CSV con periodo sovrapposto -> i movimenti gia'
    presenti diventano DUPLICATE, solo i nuovi vengono importati."""
    token = await _register(client, "dedup-pipe-a@example.com")
    account_id = await _create_account(client, token)

    first_id = await _upload_and_confirm(
        client,
        token,
        account_id,
        "2026-01-10,Stipendio,1500.00\n"
        "2026-01-20,Affitto,-800.00\n"
        "2026-01-25,Supermercato,-60.00\n",
    )
    first = await _run_job(client, token, first_id)
    assert first["status"] == "completed"
    assert first["transactions_imported"] == 3
    assert first["transactions_duplicate"] == 0
    assert first["transactions_review_pending"] == 0

    second_id = await _upload_and_confirm(
        client,
        token,
        account_id,
        "2026-01-20,Affitto,-800.00\n"
        "2026-01-25,Supermercato,-60.00\n"
        "2026-02-01,Bolletta luce,-45.00\n",
    )
    second = await _run_job(client, token, second_id)
    assert second["status"] == "completed"
    assert second["transactions_imported"] == 1
    assert second["transactions_duplicate"] == 2
    assert second["transactions_review_pending"] == 0

    transactions = await client.get(
        "/api/v1/transactions",
        params={"financial_account_id": account_id, "limit": 500},
        headers=_auth_headers(token),
    )
    # 3 dal primo import + 1 solo nuovo dal secondo (Affitto/Supermercato non
    # duplicati una seconda volta) — mai 6.
    assert len(transactions.json()) == 4


async def test_ambiguous_row_creates_review_item_and_blocks_completion(client):
    """SPEC Test 5/10: descrizione diversa a parita' di conto/data/importo/
    tipo -> REVIEW, l'import resta 'ready_for_review' finche' non decisa."""
    token = await _register(client, "dedup-pipe-b@example.com")
    account_id = await _create_account(client, token)

    first_id = await _upload_and_confirm(client, token, account_id, "2026-02-01,Amazon EU SARL,-42.50\n")
    await _run_job(client, token, first_id)

    second_id = await _upload_and_confirm(client, token, account_id, "2026-02-01,Amazon Marketplace,-42.50\n")
    second = await _run_job(client, token, second_id)
    assert second["status"] == "ready_for_review"
    assert second["transactions_imported"] == 0
    assert second["transactions_review_pending"] == 1

    pending = await client.get(
        f"/api/v1/imports/{second_id}/review-items", headers=_auth_headers(token)
    )
    assert pending.status_code == 200
    items = pending.json()
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "pending"
    assert item["description_raw"] == "Amazon Marketplace"
    assert item["candidate"] is not None
    assert item["candidate"]["description_raw"] == "Amazon EU SARL"

    summary = await client.get(
        f"/api/v1/imports/{second_id}/review-summary", headers=_auth_headers(token)
    )
    assert summary.json() == {"pending": 1, "confirmed_new": 0, "confirmed_duplicate": 0}


async def test_keep_new_decision_persists_transaction_and_completes_import(client):
    token = await _register(client, "dedup-pipe-c@example.com")
    account_id = await _create_account(client, token)

    first_id = await _upload_and_confirm(client, token, account_id, "2026-02-01,Amazon EU SARL,-42.50\n")
    await _run_job(client, token, first_id)
    second_id = await _upload_and_confirm(client, token, account_id, "2026-02-01,Amazon Marketplace,-42.50\n")
    await _run_job(client, token, second_id)

    items = (
        await client.get(f"/api/v1/imports/{second_id}/review-items", headers=_auth_headers(token))
    ).json()
    item_id = items[0]["id"]

    decision = await client.post(
        f"/api/v1/imports/{second_id}/review-items/{item_id}/decision",
        json={"decision": "keep_new"},
        headers=_auth_headers(token),
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "confirmed_new"

    updated_import = await client.get(f"/api/v1/imports/{second_id}", headers=_auth_headers(token))
    body = updated_import.json()
    assert body["status"] == "completed"
    assert body["transactions_imported"] == 1
    assert body["transactions_review_pending"] == 0

    transactions = await client.get(
        "/api/v1/transactions",
        params={"financial_account_id": account_id, "limit": 500},
        headers=_auth_headers(token),
    )
    descriptions = {t["description_raw"] for t in transactions.json()}
    assert descriptions == {"Amazon EU SARL", "Amazon Marketplace"}


async def test_keep_new_decision_is_not_reproposed_on_a_later_identical_import(client):
    """Verifica esplicita §2 (flusso IMPORTA COMUNQUE): una volta risolta,
    la stessa coppia ambigua non deve tornare in REVIEW in un import futuro
    che ripresenta lo stesso contenuto."""
    token = await _register(client, "dedup-pipe-d@example.com")
    account_id = await _create_account(client, token)

    first_id = await _upload_and_confirm(client, token, account_id, "2026-02-01,Amazon EU SARL,-42.50\n")
    await _run_job(client, token, first_id)
    second_id = await _upload_and_confirm(client, token, account_id, "2026-02-01,Amazon Marketplace,-42.50\n")
    await _run_job(client, token, second_id)
    item_id = (
        await client.get(f"/api/v1/imports/{second_id}/review-items", headers=_auth_headers(token))
    ).json()[0]["id"]
    await client.post(
        f"/api/v1/imports/{second_id}/review-items/{item_id}/decision",
        json={"decision": "keep_new"},
        headers=_auth_headers(token),
    )

    third_id = await _upload_and_confirm(
        client,
        token,
        account_id,
        "2026-02-01,Amazon EU SARL,-42.50\n2026-02-01,Amazon Marketplace,-42.50\n",
    )
    third = await _run_job(client, token, third_id)
    assert third["status"] == "completed"
    assert third["transactions_imported"] == 0
    assert third["transactions_duplicate"] == 2
    assert third["transactions_review_pending"] == 0


async def test_mark_duplicate_decision_is_not_reproposed_on_a_later_identical_import(client):
    """Stesso principio, flusso NON IMPORTARE — qui la convergenza dipende
    davvero da `transaction_dedup_decisions` (il record scartato non lascia
    un proprio fingerprint in DB)."""
    token = await _register(client, "dedup-pipe-e@example.com")
    account_id = await _create_account(client, token)

    first_id = await _upload_and_confirm(client, token, account_id, "2026-03-01,Netflix.com,-12.99\n")
    await _run_job(client, token, first_id)
    second_id = await _upload_and_confirm(client, token, account_id, "2026-03-01,NETFLIX INTL,-12.99\n")
    await _run_job(client, token, second_id)
    item_id = (
        await client.get(f"/api/v1/imports/{second_id}/review-items", headers=_auth_headers(token))
    ).json()[0]["id"]

    decision = await client.post(
        f"/api/v1/imports/{second_id}/review-items/{item_id}/decision",
        json={"decision": "mark_duplicate"},
        headers=_auth_headers(token),
    )
    assert decision.json()["status"] == "confirmed_duplicate"
    second_after = await client.get(f"/api/v1/imports/{second_id}", headers=_auth_headers(token))
    assert second_after.json()["status"] == "completed"
    assert second_after.json()["transactions_duplicate"] == 1

    # Contenuto del file diverso byte-per-byte dal secondo upload (altrimenti
    # scatterebbe il dedup a livello di FILE, ortogonale a quello che questo
    # test vuole verificare) ma equivalente dopo il parsing: "-12.990" e
    # "-12.99" producono lo stesso Decimal quantizzato a 2 cifre, quindi lo
    # stesso fingerprint.
    third_id = await _upload_and_confirm(client, token, account_id, "2026-03-01,NETFLIX INTL,-12.990\n")
    third = await _run_job(client, token, third_id)
    assert third["status"] == "completed"
    assert third["transactions_review_pending"] == 0
    assert third["transactions_duplicate"] == 1
    assert third["transactions_imported"] == 0

    transactions = await client.get(
        "/api/v1/transactions",
        params={"financial_account_id": account_id, "limit": 500},
        headers=_auth_headers(token),
    )
    # Solo la prima Netflix.com e' mai stata realmente persistita.
    assert len(transactions.json()) == 1


async def test_review_resolution_creates_linked_investment_transaction(client):
    """Verifica esplicita §6: una riga risolta da REVIEW che matcha il
    formato Trade Republic deve generare la sua InvestmentTransaction
    collegata, esattamente come una riga NEW "normale" — mai una pipeline
    "light" che la salta."""
    token = await _register(client, "dedup-pipe-f@example.com")
    account_id = await _create_account(client, token)

    first_id = await _upload_and_confirm(
        client,
        token,
        account_id,
        '2026-03-01,"Buy trade IE00B4L5Y983 iShares Core MSCI World, quantity: 1.5",-100.00\n',
    )
    await _run_job(client, token, first_id)

    second_id = await _upload_and_confirm(
        client,
        token,
        account_id,
        '2026-03-01,"Buy trade DE000BASF111 BASF SE, quantity: 2",-100.00\n',
    )
    second = await _run_job(client, token, second_id)
    assert second["status"] == "ready_for_review"
    item_id = (
        await client.get(f"/api/v1/imports/{second_id}/review-items", headers=_auth_headers(token))
    ).json()[0]["id"]

    decision = await client.post(
        f"/api/v1/imports/{second_id}/review-items/{item_id}/decision",
        json={"decision": "keep_new"},
        headers=_auth_headers(token),
    )
    assert decision.status_code == 200

    investment_transactions = await client.get(
        "/api/v1/investment-transactions",
        params={"financial_account_id": account_id},
        headers=_auth_headers(token),
    )
    assert investment_transactions.status_code == 200
    rows = investment_transactions.json()
    assert len(rows) == 2
    quantities = sorted(Decimal(row["quantity"]) for row in rows)
    assert quantities == [Decimal("1.5"), Decimal("2")]
    assert all(row["transaction_id"] is not None for row in rows)


async def test_import_without_ai_profile_completes_without_ai_dependency(client):
    """SPEC Test 13: nessun AIProfile configurato in questo test (default
    dell'ambiente) -> il dedup engine e l'intera pipeline devono funzionare
    comunque, con ai_classification_status='skipped'."""
    token = await _register(client, "dedup-pipe-g@example.com")
    account_id = await _create_account(client, token)

    import_id = await _upload_and_confirm(client, token, account_id, "2026-04-01,Farmacia,-15.00\n")
    result = await _run_job(client, token, import_id)
    assert result["status"] == "completed"
    assert result["ai_classification_status"] == "skipped"
    assert result["ai_transactions_total"] == 0

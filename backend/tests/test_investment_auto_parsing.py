"""Test di integrazione del parsing automatico dei movimenti Trade Republic
durante un import (milestone 09c) — end-to-end upload -> confirm -> worker,
come `test_imports.py`. Usa il canale CSV (piu' semplice da guidare nei
test di un vero PDF a coordinate fisse) perche' l'aggancio e' sul solo
TESTO di `description_raw`, indipendente dal canale — vedi il commento in
`import_job.py`.
"""
from httpx import AsyncClient

from app.worker.jobs.import_job import import_job

CSV_WITH_TRADES = (
    "data,descrizione,importo\n"
    '2026-01-15,"Savings plan execution IE00B4L5Y983 iShares Core MSCI World UCITS ETF, quantity: 1.5",-150.00\n'
    '2026-02-15,"Savings plan execution IE00B4L5Y983 iShares Core MSCI World UCITS ETF, quantity: 1.5",-150.00\n'
    '2026-03-01,"Buy trade US0378331005 APPLE INC, quantity: 10",-1750.00\n'
    "2026-03-15,Supermercato Lidl,-42.50\n"
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
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def test_import_derives_investment_transactions_and_positions_from_description(client):
    token = await _register(client, "invest-autoparse@example.com")
    account_id = await _create_account(client, token)

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_WITH_TRADES.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    confirm = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    assert confirm.status_code == 200

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    user_id = me.json()["id"]
    await import_job(None, import_id, user_id)

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["status"] == "completed"
    assert detail.json()["transactions_imported"] == 4

    # Un solo asset auto-creato per ISIN (le due righe "Savings plan
    # execution" condividono lo stesso ISIN — nessun duplicato).
    assets = (await client.get("/api/v1/assets", headers=_auth_headers(token))).json()
    assert len(assets) == 2
    world_etf = next(a for a in assets if a["isin"] == "IE00B4L5Y983")
    apple = next(a for a in assets if a["isin"] == "US0378331005")
    assert world_etf["asset_type"] == "etf"
    assert apple["asset_type"] == "stock"

    movements = (
        await client.get("/api/v1/investment-transactions", headers=_auth_headers(token))
    ).json()
    assert len(movements) == 3
    assert {m["type"] for m in movements} == {"buy"}
    apple_movement = next(m for m in movements if m["asset_id"] == apple["id"])
    assert apple_movement["quantity"] == "10.0000000000"
    assert apple_movement["price"] == "175.000000"
    assert apple_movement["transaction_id"] is not None  # link verso la transazione bancaria reale

    positions = (
        await client.get("/api/v1/positions", headers=_auth_headers(token))
    ).json()
    assert len(positions) == 2
    world_position = next(p for p in positions if p["asset_id"] == world_etf["id"])
    assert world_position["quantity"] == "3.0000000000"
    assert world_position["average_cost"] == "100.000000"

    # La transazione bancaria "normale" (non un trade) non genera nulla in
    # piu' del solito.
    transactions = (
        await client.get(
            "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
        )
    ).json()
    lidl = next(t for t in transactions if t["description_raw"] == "Supermercato Lidl")
    assert lidl["transaction_type"] == "expense"

    # Rework tassonomia/pipeline: le righe di trade vengono classificate
    # come Investimenti dal livello 2 della pipeline (riconoscimento
    # testuale via trade_parsing, indipendente da transaction_type — il
    # canale CSV assegna sempre "expense" alle righe debit, MAI
    # "investment", vedi csv_import.py:197). Prima di questo rework
    # sarebbero rimaste category_id NULL e sarebbero finite all'AI, che
    # potendo scegliere solo tra categorie di spesa le avrebbe classificate
    # in modo insensato (bug reale riportato dall'utente su un PAC ETF).
    categories = (await client.get("/api/v1/categories", headers=_auth_headers(token))).json()
    category_by_id = {c["id"]: c["code"] for c in categories}
    pac_rows = [t for t in transactions if t["description_raw"].startswith("Savings plan execution")]
    assert len(pac_rows) == 2
    for row in pac_rows:
        assert row["category_id"] is not None
        assert category_by_id[row["category_id"]] == "investimenti.versamento_pac"
    buy_row = next(t for t in transactions if t["description_raw"].startswith("Buy trade"))
    assert category_by_id[buy_row["category_id"]] == "investimenti.acquisto_titoli"

    # Nessun profilo AI attivo in questo test: nessuna riga viene comunque
    # accodata alla classificazione AI (Lidl resta semplicemente senza
    # categoria, non "in attesa di AI").
    detail_after = (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).json()
    assert detail_after["ai_classification_status"] == "skipped"


async def test_backfill_derives_movements_from_transactions_created_before_this_feature(client):
    """Simula transazioni 'investment' create manualmente (equivalente a un
    import avvenuto prima che il parsing automatico esistesse, M09c):
    nessun InvestmentTransaction collegato finche' non si esegue il
    backfill esplicitamente."""
    token = await _register(client, "invest-backfill@example.com")
    account_id = await _create_account(client, token)

    async def _create_manual_transaction(description: str, amount: str) -> None:
        response = await client.post(
            "/api/v1/transactions",
            json={
                "financial_account_id": account_id,
                "transaction_date": "2026-01-10",
                "description_raw": description,
                "amount": amount,
                "currency": "EUR",
                "direction": "debit" if amount.startswith("-") else "credit",
                "transaction_type": "investment",
            },
            headers=_auth_headers(token),
        )
        assert response.status_code == 201, response.text

    await _create_manual_transaction(
        "Buy trade US0378331005 APPLE INC, quantity: 5", "-875.00"
    )
    await _create_manual_transaction("Bonifico ricevuto", "500.00")  # non riconoscibile

    # Prima del backfill: nessun movimento derivato.
    before = (await client.get("/api/v1/investment-transactions", headers=_auth_headers(token))).json()
    assert before == []

    backfill_resp = await client.post("/api/v1/investment-transactions/backfill", headers=_auth_headers(token))
    assert backfill_resp.status_code == 200, backfill_resp.text
    result = backfill_resp.json()
    assert result["scanned"] == 2
    assert result["created"] == 1
    assert result["skipped_unrecognized"] == 1
    assert result["skipped_already_linked"] == 0

    movements = (await client.get("/api/v1/investment-transactions", headers=_auth_headers(token))).json()
    assert len(movements) == 1
    assert movements[0]["quantity"] == "5.0000000000"

    positions = (await client.get("/api/v1/positions", headers=_auth_headers(token))).json()
    assert len(positions) == 1
    assert positions[0]["quantity"] == "5.0000000000"

    # Idempotenza: rieseguirlo non duplica nulla.
    second_run = await client.post("/api/v1/investment-transactions/backfill", headers=_auth_headers(token))
    assert second_run.json()["created"] == 0
    assert second_run.json()["skipped_already_linked"] == 1
    movements_after = (await client.get("/api/v1/investment-transactions", headers=_auth_headers(token))).json()
    assert len(movements_after) == 1


async def test_unrecognized_investment_description_leaves_transaction_untouched(client):
    """Una riga che non matcha il formato riconosciuto resta una normale
    transazione, senza InvestmentTransaction collegata — mai un errore."""
    token = await _register(client, "invest-autoparse-none@example.com")
    account_id = await _create_account(client, token)
    csv_content = "data,descrizione,importo\n2026-01-15,Bonifico ricevuto,500.00\n"

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", csv_content.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    movements = (
        await client.get("/api/v1/investment-transactions", headers=_auth_headers(token))
    ).json()
    assert movements == []
    assets = (await client.get("/api/v1/assets", headers=_auth_headers(token))).json()
    assert assets == []


async def test_delete_import_removes_auto_created_investment_transactions_but_keeps_manual_links(client):
    """Rework 'elimina import': i movimenti di investimento AUTO-CREATI dal
    parser durante l'import (source_type_raw popolato) sono conseguenza
    dell'import stesso — vanno cancellati con lui e la posizione ricalcolata.
    Un movimento inserito/collegato A MANO dall'utente (nessun
    source_type_raw), anche se collegato a una transazione di questo
    import, NON e' creato dall'import: resta, solo scollegato dalla
    transazione che sta per essere cancellata. Bug reale scoperto sui dati
    veri dell'utente: senza scollegare esplicitamente PRIMA di cancellare le
    transazioni, la FK composita (workspace_id, transaction_id) con
    ON DELETE SET NULL azzererebbe anche workspace_id (NOT NULL), facendo
    fallire l'intera DELETE con una violazione di vincolo."""
    token = await _register(client, "invest-delete-cascade@example.com")
    account_id = await _create_account(client, token)

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_WITH_TRADES.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    transactions = (
        await client.get(
            "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
        )
    ).json()
    lidl_transaction = next(t for t in transactions if t["description_raw"] == "Supermercato Lidl")

    assets = (await client.get("/api/v1/assets", headers=_auth_headers(token))).json()
    world_etf = next(a for a in assets if a["isin"] == "IE00B4L5Y983")
    apple = next(a for a in assets if a["isin"] == "US0378331005")

    # Movimento MANUALE dell'utente, collegato a mano alla transazione Lidl
    # (scenario plausibile: una riconciliazione manuale) — non deve mai
    # essere trattato come "creato dall'import" solo perche' e' collegato a
    # una sua transazione.
    manual = await client.post(
        "/api/v1/investment-transactions",
        json={
            "financial_account_id": account_id,
            "asset_id": apple["id"],
            "transaction_id": lidl_transaction["id"],
            "trade_date": "2026-03-15",
            "type": "buy",
            "quantity": "1",
            "price": "100",
            "amount": "-100.00",
            "currency": "EUR",
        },
        headers=_auth_headers(token),
    )
    assert manual.status_code == 201
    manual_id = manual.json()["id"]

    movements_before = (
        await client.get("/api/v1/investment-transactions", headers=_auth_headers(token))
    ).json()
    assert len(movements_before) == 4  # 3 auto-creati (2 ETF + 1 Apple) + 1 manuale

    response = await client.delete(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["deleted_transactions_count"] == 4

    movements_after = (
        await client.get("/api/v1/investment-transactions", headers=_auth_headers(token))
    ).json()
    assert [m["id"] for m in movements_after] == [manual_id]
    assert movements_after[0]["transaction_id"] is None  # scollegato, mai cancellato

    positions = (await client.get("/api/v1/positions", headers=_auth_headers(token))).json()
    assert next((p for p in positions if p["asset_id"] == world_etf["id"]), None) is None
    apple_position = next(p for p in positions if p["asset_id"] == apple["id"])
    assert apple_position["quantity"] == "1.0000000000"  # solo il movimento manuale resta

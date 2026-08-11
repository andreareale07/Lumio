"""Test degli endpoint di storico IBAN (milestone 09.5c) — aggiunta
MANUALE di un IBAN storico, per chi imposta un conto per la prima volta
conoscendo gia' un IBAN precedente (distinta dalla storicizzazione
automatica testata in test_accounts_iban_reapply.py).
"""
from httpx import AsyncClient

from app.worker.jobs.import_job import import_job
from tests.fixtures.trade_republic_pdf import build_transfer_fixture_pdf


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_add_list_and_delete_iban_history(client):
    token = await _register(client, "iban-hist-crud@example.com")
    account = await client.post(
        "/api/v1/accounts",
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR", "iban": "IT31U0760116700001099179999"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    empty = await client.get(f"/api/v1/accounts/{account_id}/iban-history", headers=_auth_headers(token))
    assert empty.status_code == 200
    assert empty.json() == []

    add = await client.post(
        f"/api/v1/accounts/{account_id}/iban-history",
        json={"iban": "DE44 5001 0517 5407 3249 31"},
        headers=_auth_headers(token),
    )
    assert add.status_code == 201, add.text
    entry = add.json()
    assert entry["iban"] == "DE44500105175407324931"  # normalizzato (maiuscolo, senza spazi)

    listed = await client.get(f"/api/v1/accounts/{account_id}/iban-history", headers=_auth_headers(token))
    assert [e["iban"] for e in listed.json()] == ["DE44500105175407324931"]

    delete = await client.delete(
        f"/api/v1/accounts/{account_id}/iban-history/{entry['id']}", headers=_auth_headers(token)
    )
    assert delete.status_code == 204

    after_delete = await client.get(f"/api/v1/accounts/{account_id}/iban-history", headers=_auth_headers(token))
    assert after_delete.json() == []


async def test_add_iban_history_rejects_the_current_iban(client):
    token = await _register(client, "iban-hist-reject-current@example.com")
    account = await client.post(
        "/api/v1/accounts",
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR", "iban": "IT31U0760116700001099179999"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    response = await client.post(
        f"/api/v1/accounts/{account_id}/iban-history",
        json={"iban": "IT31U0760116700001099179999"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


async def test_add_iban_history_rejects_invalid_format(client):
    token = await _register(client, "iban-hist-reject-invalid@example.com")
    account = await client.post(
        "/api/v1/accounts",
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    response = await client.post(
        f"/api/v1/accounts/{account_id}/iban-history",
        json={"iban": "not-an-iban"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_manually_added_historical_iban_retroactively_recognizes_past_transfer(client):
    """Scenario reale: l'utente imposta il conto per la prima volta con
    l'IBAN ATTUALE (italiano) ma conosce gia' un IBAN precedente
    (tedesco, es. l'istituto l'ha cambiato prima ancora che l'utente
    iniziasse a usare Lumio) — importando un estratto conto storico che
    riporta ancora il vecchio IBAN, il bonifico deve essere riconosciuto
    come interno una volta aggiunto quell'IBAN allo storico."""
    token = await _register(client, "iban-hist-retro@example.com")
    account = await client.post(
        "/api/v1/accounts",
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR", "iban": "IT31U0760116700001099179999"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    # Estratto conto storico: il bonifico in entrata riporta il vecchio IBAN
    # tedesco, non quello italiano attuale del conto.
    pdf = build_transfer_fixture_pdf(
        outgoing_name="Luca Bianchi",
        outgoing_iban="IT99Z9999999999999999999999",
        incoming_name="Mario Rossi",
        incoming_iban="DE44500105175407324931",
    )
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto_storico.pdf", pdf, "application/pdf")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    await client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=_auth_headers(token))
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    before = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    by_description_before = {t["description_raw"]: t["transaction_type"] for t in before.json()}
    assert by_description_before["Incoming transfer for Mario Rossi (DE44500105175407324931)"] == "income"

    # L'utente aggiunge ORA l'IBAN tedesco come storico — deve rimappare subito.
    add = await client.post(
        f"/api/v1/accounts/{account_id}/iban-history",
        json={"iban": "DE44500105175407324931"},
        headers=_auth_headers(token),
    )
    assert add.status_code == 201

    after = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    by_description_after = {t["description_raw"]: t["transaction_type"] for t in after.json()}
    assert by_description_after["Incoming transfer for Mario Rossi (DE44500105175407324931)"] == "transfer"

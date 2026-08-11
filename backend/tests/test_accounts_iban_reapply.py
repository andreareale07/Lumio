"""Test dell'endpoint conti per il riconoscimento retroattivo dei
trasferimenti interni (milestone 09.5b, SPEC §37): aggiungere l'IBAN di un
conto DOPO che un estratto conto e' gia' stato importato deve rimappare
subito le transazioni che ora risultano trasferimenti riconoscibili — via
API, non solo a livello di servizio (vedi test_transfer_recognition.py per
la logica di riconoscimento in isolamento).
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


async def test_adding_iban_after_import_retroactively_marks_matching_transaction_as_transfer(client):
    token = await _register(client, "acc-iban-reapply@example.com")
    account = await client.post(
        "/api/v1/accounts",
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    pdf = build_transfer_fixture_pdf(
        outgoing_name="Luca Bianchi",
        outgoing_iban="IT99Z9999999999999999999999",
        incoming_name="Mario Rossi",
        incoming_iban="IT31U0760116700001099179999",
    )
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.pdf", pdf, "application/pdf")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    await client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=_auth_headers(token))
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    # Al momento dell'import il conto non aveva ancora un IBAN registrato:
    # il bonifico in entrata non e' riconosciuto, resta il default onesto.
    before = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    by_description_before = {t["description_raw"]: t["transaction_type"] for t in before.json()}
    assert by_description_before["Incoming transfer for Mario Rossi (IT31U0760116700001099179999)"] == "income"

    # L'utente registra ORA l'IBAN del conto — deve rimappare subito.
    update = await client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"iban": "IT31U0760116700001099179999"},
        headers=_auth_headers(token),
    )
    assert update.status_code == 200

    after = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    by_description_after = {t["description_raw"]: t["transaction_type"] for t in after.json()}
    assert by_description_after["Incoming transfer for Mario Rossi (IT31U0760116700001099179999)"] == "transfer"
    # Il bonifico verso terzi non viene toccato dal nuovo IBAN (e' un IBAN diverso).
    assert by_description_after["Outgoing transfer for Luca Bianchi (IT99Z9999999999999999999999)"] == "expense"

"""DoD milestone 05: PDF Trade Republic reale importato correttamente
end-to-end (qui con il fixture sintetico — vedi tests/fixtures/trade_republic_pdf.py
per i motivi di privacy) via upload -> confirm -> worker -> transazioni, piu'
i rifiuti di sicurezza richiesti esplicitamente dal DoD e da SPEC §53.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.worker.jobs.import_job import import_job
from tests.fixtures.trade_republic_pdf import (
    build_fixture_pdf,
    build_non_pdf_bytes_with_pdf_looking_name,
    build_transfer_fixture_pdf,
)

PDF_SAMPLE = build_fixture_pdf()


async def _register(client, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Trade Republic", "account_type": "brokerage", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def _upload_pdf(client, token: str, account_id: str, content: bytes, filename: str = "estratto.pdf"):
    return await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": (filename, content, "application/pdf")},
        headers=_auth_headers(token),
    )


def _build_pdf_without_trade_republic_markers() -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.drawString(75, 800, "ALTRA BANCA S.P.A. — ESTRATTO CONTO")
    c.showPage()
    c.save()
    return buffer.getvalue()


async def test_upload_pdf_recognizes_bank_and_returns_preview(client):
    token = await _register(client, "pdfimp-upload@example.com")
    account_id = await _create_account(client, token)

    response = await _upload_pdf(client, token, account_id, PDF_SAMPLE)

    assert response.status_code == 201
    body = response.json()
    assert body["import"]["status"] == "uploaded"
    assert body["import"]["file_type"] == "pdf"
    assert body["import"]["bank_id"] is not None
    assert body["import"]["bank_parser_id"] is not None
    assert body["preview"]["detected_bank_code"] == "trade_republic"
    assert body["preview"]["detected_bank_name"] == "Trade Republic"
    # Nessuna mappatura da scegliere per il canale pdf.
    assert body["preview"]["columns"] == []
    assert body["preview"]["suggested_mapping"] is None


async def test_confirm_pdf_queues_job_and_worker_creates_transactions(client):
    token = await _register(client, "pdfimp-confirm@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload_pdf(client, token, account_id, PDF_SAMPLE)
    import_id = upload.json()["import"]["id"]

    # Nessuna mappatura da inviare per il canale pdf: body vuoto.
    confirm = await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={}, headers=_auth_headers(token)
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "queued"
    assert confirm.json()["job_id"]

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["status"] == "completed"
    assert detail.json()["transactions_imported"] == 5
    assert detail.json()["period_start"] == "2026-05-01"
    assert detail.json()["period_end"] == "2026-05-05"

    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    descriptions = {t["description_raw"] for t in transactions.json()}
    assert "Cash reward allocation" in descriptions
    assert "Stamp Duty Tax" in descriptions
    types = {t["transaction_type"] for t in transactions.json()}
    # "Bonifico" non mappa piu' su "transfer" (hotfix pre-M09: uno strumento
    # di pagamento non e' un tipo semantico) — la riga "Incoming transfer
    # test" e' credit, quindi ricade su "income" insieme a "Premio".
    assert types == {"income", "interest", "investment", "tax"}


async def test_transfer_to_own_iban_recognized_transfer_to_third_party_stays_expense(client):
    """Milestone 09.5b (SPEC §37): un bonifico verso un conto proprio del
    workspace (IBAN corrispondente) diventa `transfer`; uno verso terzi,
    con lo stesso TIPO "Bonifico" e nessun IBAN/nominativo riconosciuto,
    resta il default onesto attuale (entrata/uscita sul segno)."""
    token = await _register(client, "pdfimp-transfer-recognition@example.com")
    account_id = await _create_account(client, token)
    await client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"iban": "IT31U0760116700001099179999"},
        headers=_auth_headers(token),
    )

    pdf = build_transfer_fixture_pdf(
        outgoing_name="Luca Bianchi",
        outgoing_iban="IT99Z9999999999999999999999",
        incoming_name="Mario Rossi",
        incoming_iban="IT31U0760116700001099179999",
    )
    upload = await _upload_pdf(client, token, account_id, pdf, filename="estratto_trasferimenti.pdf")
    import_id = upload.json()["import"]["id"]
    await client.post(f"/api/v1/imports/{import_id}/confirm", json={}, headers=_auth_headers(token))

    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    by_description = {t["description_raw"]: t["transaction_type"] for t in transactions.json()}
    assert by_description["Outgoing transfer for Luca Bianchi (IT99Z9999999999999999999999)"] == "expense"
    assert by_description["Incoming transfer for Mario Rossi (IT31U0760116700001099179999)"] == "transfer"

    # Rework pipeline: la controparte (nome/IBAN) e' ora persistita, non
    # piu' scartata subito dopo il check is_internal_transfer — e diventa
    # il merchant, con priorita' sull'estrazione generica (che su questo
    # formato di descrizione produrrebbe solo un frammento di frase
    # troncato, "Outgoing Transfer For Luca", non il vero nome).
    by_row = {t["description_raw"]: t for t in transactions.json()}
    outgoing = by_row["Outgoing transfer for Luca Bianchi (IT99Z9999999999999999999999)"]
    incoming = by_row["Incoming transfer for Mario Rossi (IT31U0760116700001099179999)"]
    assert outgoing["counterparty_name"] == "Luca Bianchi"
    assert outgoing["counterparty_iban"] == "IT99Z9999999999999999999999"
    assert outgoing["merchant"] == "Luca Bianchi"
    assert incoming["counterparty_name"] == "Mario Rossi"
    assert incoming["counterparty_iban"] == "IT31U0760116700001099179999"
    assert incoming["merchant"] == "Mario Rossi"


async def test_pdf_upload_dedup_same_as_csv(client):
    token = await _register(client, "pdfimp-dedup@example.com")
    account_id = await _create_account(client, token)

    first = await _upload_pdf(client, token, account_id, PDF_SAMPLE)
    assert first.status_code == 201

    second = await _upload_pdf(client, token, account_id, PDF_SAMPLE)
    assert second.status_code == 409
    assert second.json()["detail"]["existing_import_id"] == first.json()["import"]["id"]


async def test_reject_non_pdf_content_even_with_pdf_filename(client):
    # DoD esplicito: "file non-PDF con estensione .pdf rifiutato in modo
    # sicuro" — qui il file e' un binario PNG, non un PDF, indipendentemente
    # dal nome/Content-Type dichiarati dal client.
    token = await _register(client, "pdfimp-fake@example.com")
    account_id = await _create_account(client, token)

    response = await _upload_pdf(
        client, token, account_id, build_non_pdf_bytes_with_pdf_looking_name(), filename="finto.pdf"
    )

    assert response.status_code == 415


async def test_reject_pdf_with_forged_magic_bytes_but_invalid_structure(client):
    # SPEC §53: "non assumere che un file con estensione .pdf sia realmente
    # un PDF valido" — qui il magic byte %PDF- e' presente ma il resto del
    # file non e' una struttura PDF apribile.
    token = await _register(client, "pdfimp-corrupt@example.com")
    account_id = await _create_account(client, token)

    response = await _upload_pdf(
        client, token, account_id, b"%PDF-1.4\nnon e' una struttura PDF valida, solo rumore\n%%EOF"
    )

    assert response.status_code == 422


async def test_reject_pdf_from_unrecognized_bank(client):
    token = await _register(client, "pdfimp-unknownbank@example.com")
    account_id = await _create_account(client, token)

    response = await _upload_pdf(client, token, account_id, _build_pdf_without_trade_republic_markers())

    assert response.status_code == 422


async def test_reject_pdf_exceeding_size_limit(client, monkeypatch):
    import app.api.v1.imports as imports_module
    from app.core.config import Settings

    tiny_settings = Settings(
        database_url="postgresql+asyncpg://x", redis_url="redis://x", secret_key="x",
        max_import_file_size_bytes=10,
    )
    monkeypatch.setattr(imports_module, "get_settings", lambda: tiny_settings)

    token = await _register(client, "pdfimp-toolarge@example.com")
    account_id = await _create_account(client, token)

    response = await _upload_pdf(client, token, account_id, PDF_SAMPLE)

    assert response.status_code == 413


async def test_pdf_confirm_ignores_csv_mapping_fields(client):
    # Un body di conferma con campi mapping csv non deve rompere il flusso
    # pdf (che li ignora semplicemente, non essendo file_type='csv').
    token = await _register(client, "pdfimp-ignoremapping@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload_pdf(client, token, account_id, PDF_SAMPLE)
    import_id = upload.json()["import"]["id"]

    confirm = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"save_as": "Ignorato per il canale pdf"},
        headers=_auth_headers(token),
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "queued"


async def test_get_import_file_returns_original_pdf_bytes(client):
    """Rework 'elimina import': il viewer del file originale deve
    funzionare anche per il canale PDF, non solo CSV (content-type
    corretto, byte identici a quelli caricati)."""
    token = await _register(client, "pdfimp-file@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload_pdf(client, token, account_id, PDF_SAMPLE)
    import_id = upload.json()["import"]["id"]

    response = await client.get(f"/api/v1/imports/{import_id}/file", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == PDF_SAMPLE


async def test_get_import_file_content_rejects_pdf_import(client):
    token = await _register(client, "pdfimp-file-content@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload_pdf(client, token, account_id, PDF_SAMPLE)
    import_id = upload.json()["import"]["id"]

    response = await client.get(f"/api/v1/imports/{import_id}/file-content", headers=_auth_headers(token))
    assert response.status_code == 400

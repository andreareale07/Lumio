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
    assert types == {"income", "interest", "investment", "transfer", "tax"}


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

import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.db.base import async_session_factory
from app.services.import_paths import original_file_path
from app.storage import get_storage
from app.worker.jobs.import_job import import_job

CSV_SAMPLE = (
    "data,descrizione,importo\n"
    "2026-01-15,Supermercato Lidl,-42.50\n"
    "2026-01-16,Stipendio,1500.00\n"
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


async def _upload(client: AsyncClient, token: str, account_id: str, content: bytes, filename: str = "estratto.csv"):
    return await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": (filename, content, "text/csv")},
        headers=_auth_headers(token),
    )


async def test_upload_returns_preview_with_suggested_mapping(client):
    token = await _register(client, "imp-upload@example.com")
    account_id = await _create_account(client, token)

    response = await _upload(client, token, account_id, CSV_SAMPLE.encode())

    assert response.status_code == 201
    body = response.json()
    assert body["import"]["status"] == "uploaded"
    assert body["import"]["filename"] == "estratto.csv"
    assert body["import"]["file_size"] == len(CSV_SAMPLE.encode())
    assert body["preview"]["columns"] == ["data", "descrizione", "importo"]
    assert len(body["preview"]["sample_rows"]) == 2
    assert body["preview"]["suggested_mapping"]["columns"]["transaction_date"] == "data"
    assert body["preview"]["available_mappings"] == []


async def test_confirm_queues_job_and_worker_creates_transactions(client):
    token = await _register(client, "imp-confirm@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    confirm = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )

    assert confirm.status_code == 200
    confirmed = confirm.json()
    assert confirmed["status"] == "queued"
    assert confirmed["job_id"]
    assert confirmed["mapping_config"]["columns"]["transaction_date"] == "data"

    # Nessun worker in esecuzione nei test (determinismo, vedi
    # ROADMAP/plan): si invoca la funzione del job direttamente, esattamente
    # cio' che arq farebbe dequeuando il job appena accodato.
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    user_id = me.json()["id"]
    await import_job(None, import_id, user_id)

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["status"] == "completed"
    assert detail.json()["transactions_found"] == 2
    assert detail.json()["transactions_imported"] == 2
    assert detail.json()["period_start"] == "2026-01-15"
    assert detail.json()["period_end"] == "2026-01-16"

    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    rows = transactions.json()
    assert len(rows) == 2
    lidl = next(r for r in rows if r["amount"] == "-42.50")
    assert lidl["description_raw"] == "Supermercato Lidl"
    assert lidl["direction"] == "debit"
    assert lidl["transaction_type"] == "expense"
    assert lidl["import_id"] == import_id


async def test_confirm_on_already_confirmed_import_returns_409(client):
    token = await _register(client, "imp-doubleconfirm@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    first = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    assert second.status_code == 409


async def test_confirm_requires_exactly_one_mapping_source(client):
    token = await _register(client, "imp-badconfirm@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]

    response = await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={}, headers=_auth_headers(token)
    )
    assert response.status_code == 422


async def test_confirm_rejects_mapping_with_missing_columns(client):
    token = await _register(client, "imp-badcolumns@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    bad_mapping = upload.json()["preview"]["suggested_mapping"]
    bad_mapping["columns"]["amount"] = "colonna_inesistente"

    response = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": bad_mapping},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_confirm_can_save_mapping_for_reuse(client):
    token = await _register(client, "imp-saveas@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    confirm = await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping, "save_as": "Il mio formato banca"},
        headers=_auth_headers(token),
    )
    assert confirm.status_code == 200
    assert confirm.json()["import_mapping_id"] is not None

    mappings = await client.get("/api/v1/import-mappings", headers=_auth_headers(token))
    assert [m["name"] for m in mappings.json()] == ["Il mio formato banca"]


async def test_cancel_uploaded_import(client):
    token = await _register(client, "imp-cancel@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]

    response = await client.post(f"/api/v1/imports/{import_id}/cancel", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_cancel_completed_import_is_rejected(client):
    token = await _register(client, "imp-cancel-completed@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    response = await client.post(f"/api/v1/imports/{import_id}/cancel", headers=_auth_headers(token))
    assert response.status_code == 409


async def test_reject_binary_file_disguised_as_csv(client):
    token = await _register(client, "imp-binary@example.com")
    account_id = await _create_account(client, token)

    # PK\x03\x04 (ZIP) resta un binario "ovvio" da respingere per il canale
    # CSV. %PDF- non e' piu' un buon esempio qui dal M05 in poi: quel magic
    # byte instrada al canale PDF (vedi test_imports_pdf.py per il caso
    # "dichiara di essere un PDF ma non lo e' davvero").
    response = await _upload(client, token, account_id, b"PK\x03\x04 not a real csv", filename="finto.csv")

    assert response.status_code == 415


async def test_reject_upload_exceeding_size_limit(client, monkeypatch):
    import app.api.v1.imports as imports_module
    from app.core.config import Settings

    tiny_settings = Settings(
        database_url="postgresql+asyncpg://x", redis_url="redis://x", secret_key="x",
        max_import_file_size_bytes=10,
    )
    monkeypatch.setattr(imports_module, "get_settings", lambda: tiny_settings)

    token = await _register(client, "imp-toolarge@example.com")
    account_id = await _create_account(client, token)

    response = await _upload(client, token, account_id, CSV_SAMPLE.encode())

    assert response.status_code == 413


async def test_reject_unparseable_csv_leaves_no_import_row(client):
    token = await _register(client, "imp-unparseable@example.com")
    account_id = await _create_account(client, token)

    response = await _upload(client, token, account_id, b"\n\n\n", filename="vuoto.csv")
    assert response.status_code == 422

    listing = await client.get("/api/v1/imports", headers=_auth_headers(token))
    assert listing.json() == []


async def test_upload_rejects_foreign_account(client):
    token_a = await _register(client, "imp-cross-a@example.com")
    token_b = await _register(client, "imp-cross-b@example.com")
    account_b_id = await _create_account(client, token_b)

    response = await _upload(client, token_a, account_b_id, CSV_SAMPLE.encode())

    assert response.status_code == 400


async def test_user_a_cannot_see_user_b_import_via_api(client):
    token_a = await _register(client, "imp-visib-a@example.com")
    token_b = await _register(client, "imp-visib-b@example.com")
    account_b_id = await _create_account(client, token_b)
    upload = await _upload(client, token_b, account_b_id, CSV_SAMPLE.encode())
    import_b_id = upload.json()["import"]["id"]

    get_response = await client.get(f"/api/v1/imports/{import_b_id}", headers=_auth_headers(token_a))
    assert get_response.status_code == 404

    list_response = await client.get("/api/v1/imports", headers=_auth_headers(token_a))
    assert list_response.json() == []


async def test_user_a_cannot_read_user_b_import_file_via_preview_or_confirm(client):
    """Gap chiuso in milestone 11 (SPEC §56, 'files' tra le entita' elencate):
    a differenza di test_user_a_cannot_see_user_b_import_via_api sopra (solo
    metadata), qui si verifica che gli endpoint che leggono davvero i BYTE
    del file originale da storage (/preview, /confirm) neghino l'accesso
    allo stesso modo — mai un percorso che arrivi a get_storage().read() con
    l'import_id di un altro workspace."""
    token_a = await _register(client, "imp-file-iso-a@example.com")
    token_b = await _register(client, "imp-file-iso-b@example.com")
    account_b_id = await _create_account(client, token_b)
    upload = await _upload(client, token_b, account_b_id, CSV_SAMPLE.encode())
    import_b_id = upload.json()["import"]["id"]

    preview_response = await client.get(
        f"/api/v1/imports/{import_b_id}/preview", headers=_auth_headers(token_a)
    )
    assert preview_response.status_code == 404

    confirm_response = await client.post(
        f"/api/v1/imports/{import_b_id}/confirm", json={}, headers=_auth_headers(token_a)
    )
    assert confirm_response.status_code == 404


async def test_random_import_id_returns_404(client):
    token = await _register(client, "imp-404@example.com")
    response = await client.get(f"/api/v1/imports/{uuid.uuid4()}", headers=_auth_headers(token))
    assert response.status_code == 404


async def _set_import_status(import_id: str, status: str, user_id: str) -> None:
    """Manipola direttamente la riga per simulare uno stato ('processing')
    che il job sincrono usato nei test non si ferma mai a metà — stesso
    pattern di accesso diretto al DB già usato da test_rls_imports.py."""
    async with async_session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_id}
        )
        await session.execute(text("UPDATE imports SET status = :s WHERE id = :id"), {"s": status, "id": import_id})
        await session.commit()


async def test_delete_completed_import_removes_transactions_import_and_file(client):
    token = await _register(client, "imp-delete-completed@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    workspace_id = uuid.UUID(upload.json()["import"]["workspace_id"])
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    assert get_storage().exists(original_file_path(workspace_id, uuid.UUID(import_id), "csv")) is True

    count = await client.get(f"/api/v1/imports/{import_id}/transactions-count", headers=_auth_headers(token))
    assert count.json()["transactions_count"] == 2

    response = await client.delete(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["deleted_transactions_count"] == 2

    assert (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).status_code == 404

    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    assert transactions.json() == []

    assert get_storage().exists(original_file_path(workspace_id, uuid.UUID(import_id), "csv")) is False


async def test_delete_queued_import_succeeds_with_zero_transactions(client):
    token = await _register(client, "imp-delete-queued@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    # Nessuna invocazione di import_job: lo stato resta "queued", nessuna
    # transazione mai creata — esattamente il caso "ferma il job in coda ed
    # elimina subito", zero righe da cancellare.

    response = await client.delete(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["deleted_transactions_count"] == 0
    assert (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).status_code == 404


async def test_delete_uploaded_import_succeeds(client):
    token = await _register(client, "imp-delete-uploaded@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    # Mai confermato: status resta "uploaded", nessun job_id.

    response = await client.delete(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["deleted_transactions_count"] == 0


async def test_delete_cancelled_import_succeeds(client):
    token = await _register(client, "imp-delete-cancelled@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    await client.post(f"/api/v1/imports/{import_id}/cancel", headers=_auth_headers(token))

    response = await client.delete(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json()["deleted_transactions_count"] == 0


async def test_delete_processing_import_returns_409(client):
    """Il job worker e' realmente in esecuzione in questo stato — arq non
    ha modo di interromperlo a meta', quindi l'eliminazione va rifiutata
    esplicitamente (mai un bottone silenziosamente assente lato UI)."""
    token = await _register(client, "imp-delete-processing@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await _set_import_status(import_id, "processing", me.json()["id"])

    response = await client.delete(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert response.status_code == 409

    # Nessun effetto collaterale: la riga e le eventuali transazioni restano.
    assert (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).status_code == 200


async def test_delete_import_returns_409_while_ai_classification_running(client):
    """Rework "disaccoppiamento AI": l'import e' gia' 'completed' (le
    transazioni esistono), ma il job separato di classificazione AI sta
    ancora scrivendo su QUELLE STESSE transazioni — stessa impossibilita' di
    interromperlo a meta' del job di import 'processing'/'parsing', quindi
    stesso rifiuto esplicito (409), mai una corsa silenziosa tra la sua
    scrittura e la DELETE."""
    token = await _register(client, "imp-delete-ai-running@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    async with async_session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": me.json()["id"]}
        )
        await session.execute(
            text("UPDATE imports SET ai_classification_status = 'running' WHERE id = :id"), {"id": import_id}
        )
        await session.commit()

    response = await client.delete(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert response.status_code == 409

    # Nessun effetto collaterale: la riga e le transazioni restano.
    assert (await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))).status_code == 200


async def test_delete_cross_tenant_returns_404_and_does_not_touch_other_workspace(client):
    token_a = await _register(client, "imp-delete-cross-a@example.com")
    token_b = await _register(client, "imp-delete-cross-b@example.com")
    account_b_id = await _create_account(client, token_b)
    upload = await _upload(client, token_b, account_b_id, CSV_SAMPLE.encode())
    import_b_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_b_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token_b)
    )
    me_b = await client.get("/api/v1/auth/me", headers=_auth_headers(token_b))
    await import_job(None, import_b_id, me_b.json()["id"])

    response = await client.delete(f"/api/v1/imports/{import_b_id}", headers=_auth_headers(token_a))
    assert response.status_code == 404

    still_there = await client.get(f"/api/v1/imports/{import_b_id}", headers=_auth_headers(token_b))
    assert still_there.status_code == 200
    assert still_there.json()["status"] == "completed"


async def test_get_import_file_returns_original_csv_bytes(client):
    token = await _register(client, "imp-file@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]

    response = await client.get(f"/api/v1/imports/{import_id}/file", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content == CSV_SAMPLE.encode()


async def test_get_import_file_cross_tenant_returns_404(client):
    token_a = await _register(client, "imp-file-cross-a@example.com")
    token_b = await _register(client, "imp-file-cross-b@example.com")
    account_b_id = await _create_account(client, token_b)
    upload = await _upload(client, token_b, account_b_id, CSV_SAMPLE.encode())
    import_b_id = upload.json()["import"]["id"]

    response = await client.get(f"/api/v1/imports/{import_b_id}/file", headers=_auth_headers(token_a))
    assert response.status_code == 404


async def test_get_import_file_content_returns_full_csv_as_table(client):
    token = await _register(client, "imp-file-content@example.com")
    account_id = await _create_account(client, token)
    upload = await _upload(client, token, account_id, CSV_SAMPLE.encode())
    import_id = upload.json()["import"]["id"]

    response = await client.get(f"/api/v1/imports/{import_id}/file-content", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["data", "descrizione", "importo"]
    assert body["total_rows"] == 2
    assert body["truncated"] is False
    assert body["rows"] == [
        ["2026-01-15", "Supermercato Lidl", "-42.50"],
        ["2026-01-16", "Stipendio", "1500.00"],
    ]

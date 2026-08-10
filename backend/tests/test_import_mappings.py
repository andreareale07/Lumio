from app.worker.jobs.import_csv import import_csv_job

CSV_SAMPLE = "data,descrizione,importo\n2026-01-15,Spesa,-10.00\n"

_MAPPING_CONFIG = {
    "columns": {"transaction_date": "data", "description_raw": "descrizione", "amount": "importo"},
}


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
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    return response.json()["id"]


async def test_create_list_update_delete_mapping(client):
    token = await _register(client, "map-crud@example.com")
    account_id = await _create_account(client, token)

    create = await client.post(
        "/api/v1/import-mappings",
        json={"name": "Fineco standard", "financial_account_id": account_id, "config": _MAPPING_CONFIG},
        headers=_auth_headers(token),
    )
    assert create.status_code == 201
    mapping_id = create.json()["id"]

    listing = await client.get("/api/v1/import-mappings", headers=_auth_headers(token))
    assert [m["id"] for m in listing.json()] == [mapping_id]

    update = await client.patch(
        f"/api/v1/import-mappings/{mapping_id}",
        json={"name": "Fineco rinominata"},
        headers=_auth_headers(token),
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Fineco rinominata"

    delete = await client.delete(f"/api/v1/import-mappings/{mapping_id}", headers=_auth_headers(token))
    assert delete.status_code == 204

    listing_after = await client.get("/api/v1/import-mappings", headers=_auth_headers(token))
    assert listing_after.json() == []


async def test_duplicate_mapping_name_in_same_workspace_rejected(client):
    token = await _register(client, "map-dup@example.com")

    first = await client.post(
        "/api/v1/import-mappings",
        json={"name": "Standard", "config": _MAPPING_CONFIG},
        headers=_auth_headers(token),
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/import-mappings",
        json={"name": "Standard", "config": _MAPPING_CONFIG},
        headers=_auth_headers(token),
    )
    assert second.status_code == 400


async def test_user_a_cannot_see_or_modify_user_b_mapping(client):
    token_a = await _register(client, "map-cross-a@example.com")
    token_b = await _register(client, "map-cross-b@example.com")

    create = await client.post(
        "/api/v1/import-mappings",
        json={"name": "Di B", "config": _MAPPING_CONFIG},
        headers=_auth_headers(token_b),
    )
    mapping_b_id = create.json()["id"]

    get_response = await client.get(
        f"/api/v1/import-mappings/{mapping_b_id}", headers=_auth_headers(token_a)
    )
    assert get_response.status_code == 404

    update_response = await client.patch(
        f"/api/v1/import-mappings/{mapping_b_id}",
        json={"name": "Rubata"},
        headers=_auth_headers(token_a),
    )
    assert update_response.status_code == 404

    delete_response = await client.delete(
        f"/api/v1/import-mappings/{mapping_b_id}", headers=_auth_headers(token_a)
    )
    assert delete_response.status_code == 404


async def test_successful_import_suggests_its_mapping_for_next_upload_on_same_account(client):
    token = await _register(client, "map-suggest@example.com")
    account_id = await _create_account(client, token)

    upload1 = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("uno.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import1_id = upload1.json()["import"]["id"]
    confirm1 = await client.post(
        f"/api/v1/imports/{import1_id}/confirm",
        json={"mapping": upload1.json()["preview"]["suggested_mapping"], "save_as": "La mia mappatura"},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_csv_job(None, import1_id, me.json()["id"])

    # Un secondo file, con un contenuto diverso (altrimenti il dedup lo
    # respingerebbe), sullo stesso conto: la mappatura suggerita deve essere
    # quella dell'import completato con successo, non l'euristica.
    csv2 = "data,descrizione,importo\n2026-02-01,Altra spesa,-5.00\n"
    upload2 = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("due.csv", csv2.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    assert upload2.json()["preview"]["suggested_mapping"] == confirm1.json()["mapping_config"]

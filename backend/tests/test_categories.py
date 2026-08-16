from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_list_categories_includes_system_categories(client):
    token = await _register(client, "cat-viewer@example.com")

    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    assert response.status_code == 200
    codes = {c["code"] for c in response.json()}
    assert "casa" in codes
    assert "alimentari.supermercato" in codes


async def test_create_update_delete_custom_category(client):
    token = await _register(client, "cat-owner@example.com")

    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Hobby", "code": "hobby"},
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    category = create_response.json()
    assert category["is_system"] is False

    update_response = await client.patch(
        f"/api/v1/categories/{category['id']}",
        json={"name": "Hobby personali"},
        headers=_auth_headers(token),
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Hobby personali"

    delete_response = await client.delete(
        f"/api/v1/categories/{category['id']}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204


async def test_cannot_modify_system_category(client):
    token = await _register(client, "cat-hacker@example.com")

    list_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    system_category = next(c for c in list_response.json() if c["is_system"])

    update_response = await client.patch(
        f"/api/v1/categories/{system_category['id']}",
        json={"name": "Hacked"},
        headers=_auth_headers(token),
    )
    assert update_response.status_code == 403

    delete_response = await client.delete(
        f"/api/v1/categories/{system_category['id']}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 403


async def test_cannot_delete_category_in_use_by_a_transaction(client):
    token = await _register(client, "cat-in-use@example.com")

    account = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    category = await client.post(
        "/api/v1/categories",
        json={"name": "Hobby", "code": "hobby"},
        headers=_auth_headers(token),
    )
    category_id = category.json()["id"]

    transaction = await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id,
            "transaction_date": "2026-01-01",
            "amount": "-10.00",
            "currency": "EUR",
            "direction": "debit",
            "description_raw": "Test",
            "transaction_type": "expense",
            "category_id": category_id,
        },
        headers=_auth_headers(token),
    )
    assert transaction.status_code == 201, transaction.text

    delete_response = await client.delete(
        f"/api/v1/categories/{category_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 409

    # La categoria non deve essere stata cancellata nonostante il rollback avvenga dopo il flush del delete.
    list_response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    assert category_id in {c["id"] for c in list_response.json()}


async def _category_by_code(client: AsyncClient, token: str, code: str) -> dict:
    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    return next(c for c in response.json() if c["code"] == code)


async def test_code_is_generated_server_side_with_parent_prefix(client):
    # Rework categorie: il client non invia piu' `code` — un valore inviato
    # comunque da un client non aggiornato viene semplicemente ignorato
    # (Pydantic scarta campi extra), il server genera sempre il proprio.
    token = await _register(client, "cat-code-gen@example.com")
    trasporti = await _category_by_code(client, token, "trasporti")

    child_response = await client.post(
        "/api/v1/categories",
        json={"name": "Monopattino", "parent_id": trasporti["id"], "code": "should_be_ignored"},
        headers=_auth_headers(token),
    )
    assert child_response.status_code == 201
    assert child_response.json()["code"] == "trasporti.monopattino"


async def test_code_collision_gets_anti_collision_suffix(client):
    token = await _register(client, "cat-code-collision@example.com")

    first = await client.post(
        "/api/v1/categories", json={"name": "Varie"}, headers=_auth_headers(token)
    )
    assert first.json()["code"] == "varie"

    second = await client.post(
        "/api/v1/categories", json={"name": "Varie"}, headers=_auth_headers(token)
    )
    assert second.status_code == 201
    assert second.json()["code"] == "varie_2"


async def test_child_inherits_kind_from_parent(client):
    token = await _register(client, "cat-kind-inherit@example.com")
    trasporti = await _category_by_code(client, token, "trasporti")
    assert trasporti["kind"] == "expense"

    child_response = await client.post(
        "/api/v1/categories",
        json={"name": "Monopattino", "parent_id": trasporti["id"]},
        headers=_auth_headers(token),
    )
    assert child_response.json()["kind"] == "expense"


async def test_child_with_mismatched_kind_is_rejected(client):
    token = await _register(client, "cat-kind-mismatch@example.com")
    trasporti = await _category_by_code(client, token, "trasporti")  # kind=expense

    response = await client.post(
        "/api/v1/categories",
        json={"name": "Monopattino", "parent_id": trasporti["id"], "kind": "income"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_root_category_kind_defaults_to_expense(client):
    token = await _register(client, "cat-kind-default@example.com")
    response = await client.post(
        "/api/v1/categories", json={"name": "Varie root"}, headers=_auth_headers(token)
    )
    assert response.json()["kind"] == "expense"


async def test_root_category_can_choose_explicit_kind(client):
    token = await _register(client, "cat-kind-explicit@example.com")
    response = await client.post(
        "/api/v1/categories",
        json={"name": "Entrata personalizzata", "kind": "income"},
        headers=_auth_headers(token),
    )
    assert response.json()["kind"] == "income"


async def test_creating_child_of_a_child_is_rejected_depth_two_max(client):
    token = await _register(client, "cat-depth@example.com")
    supermercato = await _category_by_code(client, token, "alimentari.supermercato")

    response = await client.post(
        "/api/v1/categories",
        json={"name": "Troppo profonda", "parent_id": supermercato["id"]},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_cannot_set_category_as_its_own_parent(client):
    token = await _register(client, "cat-self-parent@example.com")
    created = await client.post(
        "/api/v1/categories", json={"name": "Auto-genitore"}, headers=_auth_headers(token)
    )
    category_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/categories/{category_id}",
        json={"parent_id": category_id},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_category_with_children_cannot_become_a_child_itself(client):
    token = await _register(client, "cat-reparent-with-children@example.com")
    parent = await client.post(
        "/api/v1/categories", json={"name": "Genitore custom"}, headers=_auth_headers(token)
    )
    parent_id = parent.json()["id"]
    await client.post(
        "/api/v1/categories",
        json={"name": "Figlio custom", "parent_id": parent_id},
        headers=_auth_headers(token),
    )
    other_root = await client.post(
        "/api/v1/categories", json={"name": "Altro genitore"}, headers=_auth_headers(token)
    )

    response = await client.patch(
        f"/api/v1/categories/{parent_id}",
        json={"parent_id": other_root.json()["id"]},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


async def test_renaming_does_not_regenerate_code(client):
    token = await _register(client, "cat-rename-stable-code@example.com")
    created = await client.post(
        "/api/v1/categories", json={"name": "Nome originale"}, headers=_auth_headers(token)
    )
    original_code = created.json()["code"]

    renamed = await client.patch(
        f"/api/v1/categories/{created.json()['id']}",
        json={"name": "Nome cambiato"},
        headers=_auth_headers(token),
    )
    assert renamed.json()["code"] == original_code


async def test_changing_parent_regenerates_code(client):
    token = await _register(client, "cat-reparent-regenerates-code@example.com")
    trasporti = await _category_by_code(client, token, "trasporti")
    created = await client.post(
        "/api/v1/categories", json={"name": "Da spostare"}, headers=_auth_headers(token)
    )
    assert created.json()["code"] == "da_spostare"

    moved = await client.patch(
        f"/api/v1/categories/{created.json()['id']}",
        json={"parent_id": trasporti["id"]},
        headers=_auth_headers(token),
    )
    assert moved.json()["code"] == "trasporti.da_spostare"
    assert moved.json()["kind"] == "expense"


async def test_updating_root_kind_without_specifying_it_keeps_current_value(client):
    token = await _register(client, "cat-kind-not-reset@example.com")
    created = await client.post(
        "/api/v1/categories",
        json={"name": "Entrata personalizzata", "kind": "income"},
        headers=_auth_headers(token),
    )
    category_id = created.json()["id"]

    renamed = await client.patch(
        f"/api/v1/categories/{category_id}",
        json={"name": "Entrata rinominata"},
        headers=_auth_headers(token),
    )
    # Nessun `kind` nel payload di update: non deve resettarsi silenziosamente
    # al default 'expense'.
    assert renamed.json()["kind"] == "income"


async def test_list_categories_filters_by_kind(client):
    token = await _register(client, "cat-filter-kind@example.com")
    response = await client.get(
        "/api/v1/categories", params={"kind": "income"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert all(c["kind"] == "income" for c in response.json())
    assert any(c["code"] == "entrate" for c in response.json())


async def test_list_categories_filters_by_roots_only(client):
    token = await _register(client, "cat-filter-roots@example.com")
    response = await client.get(
        "/api/v1/categories", params={"roots_only": True}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert all(c["parent_id"] is None for c in response.json())
    assert any(c["code"] == "trasporti" for c in response.json())


async def test_list_categories_filters_by_search_query(client):
    token = await _register(client, "cat-filter-search@example.com")
    response = await client.get(
        "/api/v1/categories", params={"q": "carburante"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    codes = {c["code"] for c in response.json()}
    assert "trasporti.carburante" in codes
    assert "casa" not in codes


async def test_list_categories_filters_by_is_active(client):
    token = await _register(client, "cat-filter-active@example.com")
    created = await client.post(
        "/api/v1/categories", json={"name": "Da disattivare"}, headers=_auth_headers(token)
    )
    category_id = created.json()["id"]
    await client.patch(
        f"/api/v1/categories/{category_id}", json={"is_active": False}, headers=_auth_headers(token)
    )

    active_only = await client.get(
        "/api/v1/categories", params={"is_active": True}, headers=_auth_headers(token)
    )
    assert category_id not in {c["id"] for c in active_only.json()}

    inactive_only = await client.get(
        "/api/v1/categories", params={"is_active": False}, headers=_auth_headers(token)
    )
    assert category_id in {c["id"] for c in inactive_only.json()}


async def test_user_a_cannot_modify_user_b_custom_category_via_api(client):
    token_a = await _register(client, "cat-a@example.com")
    token_b = await _register(client, "cat-b@example.com")

    create_response = await client.post(
        "/api/v1/categories",
        json={"name": "Privata di B", "code": "privata-b"},
        headers=_auth_headers(token_b),
    )
    category_b_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/api/v1/categories/{category_b_id}",
        json={"name": "Hacked"},
        headers=_auth_headers(token_a),
    )
    assert update_response.status_code == 404

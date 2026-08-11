"""Test API dei profili MarketDataProvider e dei prezzi asset (milestone
09b) — stesso pattern di `test_portfolio_api.py`.
"""
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_asset(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "Vanguard FTSE All-World", "symbol": "VWCE", "asset_type": "etf", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/assets", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Profili ------------------------------------------------------------


async def test_market_data_profile_crud(client):
    token = await _register(client, "md-crud@example.com")

    create_resp = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    profile_id = create_resp.json()["id"]
    assert create_resp.json()["is_active"] is False
    assert create_resp.json()["api_key_set"] is False

    update_resp = await client.patch(
        f"/api/v1/settings/market-data/profiles/{profile_id}",
        json={"name": "Manuale (aggiornato)"},
        headers=_auth_headers(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Manuale (aggiornato)"

    list_resp = await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    assert len(list_resp.json()) == 1


async def test_custom_provider_requires_endpoint_and_price_field(client):
    token = await _register(client, "md-custom-validation@example.com")

    missing_endpoint = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Alpha Vantage", "provider": "custom"},
        headers=_auth_headers(token),
    )
    assert missing_endpoint.status_code == 400

    missing_price_field = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Alpha Vantage", "provider": "custom", "endpoint": "https://example.invalid/{symbol}"},
        headers=_auth_headers(token),
    )
    assert missing_price_field.status_code == 400

    ok = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={
            "name": "Alpha Vantage",
            "provider": "custom",
            "endpoint": "https://example.invalid/{symbol}",
            "price_field": "price",
            "api_key": "secret-key",
        },
        headers=_auth_headers(token),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["api_key_set"] is True


async def test_activate_profile_deactivates_others(client):
    token = await _register(client, "md-activate@example.com")

    manual = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    stooq = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Stooq", "provider": "stooq"},
        headers=_auth_headers(token),
    )
    manual_id, stooq_id = manual.json()["id"], stooq.json()["id"]

    await client.post(f"/api/v1/settings/market-data/profiles/{manual_id}/activate", headers=_auth_headers(token))
    activate_resp = await client.post(
        f"/api/v1/settings/market-data/profiles/{stooq_id}/activate", headers=_auth_headers(token)
    )
    assert activate_resp.json()["is_active"] is True

    list_resp = await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    active = [p for p in list_resp.json() if p["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == stooq_id


async def test_deactivate_all_disables_market_data(client):
    token = await _register(client, "md-deactivate@example.com")
    created = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    profile_id = created.json()["id"]
    await client.post(f"/api/v1/settings/market-data/profiles/{profile_id}/activate", headers=_auth_headers(token))

    deactivate_resp = await client.post("/api/v1/settings/market-data/deactivate", headers=_auth_headers(token))
    assert deactivate_resp.status_code == 204

    list_resp = await client.get("/api/v1/settings/market-data/profiles", headers=_auth_headers(token))
    assert all(not p["is_active"] for p in list_resp.json())


async def test_test_connection_on_manual_profile_always_succeeds(client):
    token = await _register(client, "md-test-manual@example.com")
    created = await client.post(
        "/api/v1/settings/market-data/profiles",
        json={"name": "Manuale", "provider": "manual"},
        headers=_auth_headers(token),
    )
    profile_id = created.json()["id"]

    test_resp = await client.post(
        f"/api/v1/settings/market-data/profiles/{profile_id}/test", headers=_auth_headers(token)
    )
    assert test_resp.status_code == 200
    assert test_resp.json()["success"] is True


async def test_draft_test_connection_reports_missing_endpoint_without_error(client):
    token = await _register(client, "md-test-draft@example.com")
    response = await client.post(
        "/api/v1/settings/market-data/test",
        json={"provider": "custom"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["success"] is False


# --- Prezzi asset (SPEC §38 "dati manuali") --------------------------------


async def test_manual_asset_price_upsert_and_list(client):
    token = await _register(client, "md-price@example.com")
    asset_id = await _create_asset(client, token)

    create_resp = await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "100.50", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert create_resp.status_code == 200, create_resp.text
    assert create_resp.json()["source"] == "manual"
    assert create_resp.json()["price"] == "100.500000"

    # Stesso giorno: sovrascrive, non duplica.
    overwrite_resp = await client.put(
        f"/api/v1/assets/{asset_id}/prices",
        json={"price_date": "2026-08-01", "price": "101.00", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert overwrite_resp.status_code == 200

    list_resp = await client.get(f"/api/v1/assets/{asset_id}/prices", headers=_auth_headers(token))
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["price"] == "101.000000"


async def test_asset_price_rejects_asset_from_another_workspace(client):
    token_a = await _register(client, "md-price-cross-a@example.com")
    token_b = await _register(client, "md-price-cross-b@example.com")
    asset_b = await _create_asset(client, token_b)

    response = await client.put(
        f"/api/v1/assets/{asset_b}/prices",
        json={"price_date": "2026-08-01", "price": "100.00", "currency": "EUR"},
        headers=_auth_headers(token_a),
    )
    assert response.status_code == 404

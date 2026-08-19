"""Test dell'API del sistema di valute (elenco di sistema + inserimento
manuale di un tasso di cambio) — stesso pattern di `test_market_data_api.py`.
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


async def test_list_currencies_includes_seeded_system_currencies(client):
    token = await _register(client, "cur-list@example.com")
    response = await client.get("/api/v1/currencies", headers=_auth_headers(token))
    assert response.status_code == 200
    by_code = {c["code"]: c for c in response.json()}
    assert by_code["EUR"]["is_system"] is True
    assert by_code["EUR"]["symbol"] == "€"
    assert by_code["USD"]["is_system"] is True


async def test_upsert_manual_fx_rate_and_overwrite(client):
    token = await _register(client, "cur-rate@example.com")

    first = await client.put(
        "/api/v1/currencies/rates",
        json={"from_currency": "USD", "to_currency": "EUR", "rate_date": "2026-01-15", "rate": "0.92"},
        headers=_auth_headers(token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["source"] == "manual"
    assert first.json()["rate"] == "0.9200000000"

    # Stesso giorno/coppia: sovrascrive, non duplica.
    second = await client.put(
        "/api/v1/currencies/rates",
        json={"from_currency": "usd", "to_currency": "eur", "rate_date": "2026-01-15", "rate": "0.95"},
        headers=_auth_headers(token),
    )
    assert second.status_code == 200
    assert second.json()["rate"] == "0.9500000000"
    assert second.json()["from_currency"] == "USD"  # normalizzato in maiuscolo

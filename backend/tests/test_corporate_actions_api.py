"""Test API delle operazioni societarie: unione di due asset (caso reale Acme,
raggruppamento 10.000:1 con cambio ISIN) e chiusura a zero di un derivato
scaduto (turbo/knock-out)."""
from datetime import date

from httpx import AsyncClient

from tests.test_portfolio_api import (
    _auth_headers,
    _create_account,
    _create_asset,
    _create_investment_transaction,
    _register,
)


def _capture_backfill(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def fake_enqueue(workspace_id, user_id, date_from=None):
        calls.append({"date_from": date_from})
        return "fake-job"

    monkeypatch.setattr("app.api.v1.corporate_actions.enqueue_snapshot_backfill", fake_enqueue)
    return calls


async def _prepare_atos(client: AsyncClient, token: str) -> tuple[str, str, str]:
    account_id = await _create_account(client, token)
    old_asset = await _create_asset(client, token, name="ACME SE NOM. EO 1", symbol=None, asset_type="stock")
    new_asset = await _create_asset(client, token, name="ACME SE NOM.EO 1", symbol=None, asset_type="stock")
    for trade_date, qty, price, amount in (
        ("2025-01-23", "100000", "0.002500", "-250.00"),
        ("2025-03-06", "100000", "0.004500", "-450.00"),
    ):
        response = await _create_investment_transaction(
            client, token, account_id, asset_id=old_asset, trade_date=trade_date, quantity=qty, price=price, amount=amount
        )
        assert response.status_code == 201, response.text
    return account_id, old_asset, new_asset


async def test_merge_assets_applies_split_and_lets_the_sale_close_the_position(client, monkeypatch):
    backfill_calls = _capture_backfill(monkeypatch)
    token = await _register(client, "merge-atos@example.com")
    account_id, old_asset, new_asset = await _prepare_atos(client, token)

    # La vendita sul nuovo ISIN, senza lo split, e' una vendita scoperta: l'API
    # manuale la rifiuta (come l'import la lascia in posizione negativa).
    uncovered = await _create_investment_transaction(
        client, token, account_id, asset_id=new_asset, trade_date="2025-04-28", type="sell",
        quantity="20", price="34.90", amount="698.00",
    )
    assert uncovered.status_code == 400

    merge = await client.post(
        "/api/v1/corporate-actions/merge-assets",
        json={"source_asset_id": old_asset, "target_asset_id": new_asset, "ratio": "0.0001", "split_date": "2025-04-27"},
        headers=_auth_headers(token),
    )
    assert merge.status_code == 204, merge.text
    # Gli snapshot del patrimonio vanno ricostruiti dal primo movimento spostato.
    assert backfill_calls == [{"date_from": date(2025, 1, 23)}]

    positions = (await client.get("/api/v1/positions", headers=_auth_headers(token))).json()
    assert [p["asset_id"] for p in positions] == [new_asset]
    assert positions[0]["quantity"] == "20.0000000000"
    assert positions[0]["average_cost"] == "35.600000"

    sell = await _create_investment_transaction(
        client, token, account_id, asset_id=new_asset, trade_date="2025-04-28", type="sell",
        quantity="20", price="34.90", amount="698.00",
    )
    assert sell.status_code == 201, sell.text
    closed = (
        await client.get("/api/v1/positions", params={"only_open": "false"}, headers=_auth_headers(token))
    ).json()
    assert closed[0]["quantity"] == "0.0000000000"
    assert closed[0]["realized_pl"] == "-1.60"


async def test_merge_rejects_same_asset_and_overlapping_dates(client):
    token = await _register(client, "merge-reject@example.com")
    account_id = await _create_account(client, token)
    first = await _create_asset(client, token, name="Alfa", symbol="ALFA")
    second = await _create_asset(client, token, name="Alfa B", symbol="ALFB")
    for asset in (first, second):
        await _create_investment_transaction(client, token, account_id, asset_id=asset, trade_date="2026-01-15")

    same = await client.post(
        "/api/v1/corporate-actions/merge-assets",
        json={"source_asset_id": first, "target_asset_id": first, "ratio": "2"},
        headers=_auth_headers(token),
    )
    assert same.status_code == 400

    overlapping = await client.post(
        "/api/v1/corporate-actions/merge-assets",
        json={"source_asset_id": first, "target_asset_id": second, "ratio": "2"},
        headers=_auth_headers(token),
    )
    assert overlapping.status_code == 400
    assert "sovrappongono" in overlapping.json()["detail"]


async def test_merge_is_isolated_between_workspaces(client):
    owner = await _register(client, "merge-owner@example.com")
    intruder = await _register(client, "merge-intruder@example.com")
    account_id = await _create_account(client, owner)
    first = await _create_asset(client, owner, name="Alfa", symbol="ALFA")
    second = await _create_asset(client, owner, name="Alfa B", symbol="ALFB")
    await _create_investment_transaction(client, owner, account_id, asset_id=first, trade_date="2026-01-15")

    response = await client.post(
        "/api/v1/corporate-actions/merge-assets",
        json={"source_asset_id": first, "target_asset_id": second, "ratio": "2", "split_date": "2026-02-01"},
        headers=_auth_headers(intruder),
    )
    assert response.status_code == 400
    owner_positions = (await client.get("/api/v1/positions", headers=_auth_headers(owner))).json()
    assert [p["asset_id"] for p in owner_positions] == [first]


async def test_expiry_suggestion_and_close_worthless_derivative(client, monkeypatch):
    backfill_calls = _capture_backfill(monkeypatch)
    token = await _register(client, "expire-turbo@example.com")
    account_id = await _create_account(client, token)
    turbo = await _create_asset(
        client, token, name="Turbo auf EXAMPLE CORP. DL-,10", symbol=None, asset_type="other"
    )
    etf = await _create_asset(client, token, name="Vanguard FTSE All-World", symbol="VWCE")
    await _create_investment_transaction(
        client, token, account_id, asset_id=turbo, trade_date="2026-03-02", quantity="100", price="0.25", amount="-25.00"
    )
    await _create_investment_transaction(client, token, account_id, asset_id=etf, trade_date="2026-03-02")

    suggestions = (await client.get("/api/v1/corporate-actions/suggestions", headers=_auth_headers(token))).json()
    assert [e["asset_id"] for e in suggestions["expirations"]] == [turbo]
    assert suggestions["expirations"][0]["quantity"] == "100.0000000000"

    expire = await client.post(
        "/api/v1/corporate-actions/expire",
        json={"asset_id": turbo, "expiry_date": "2026-03-20"},
        headers=_auth_headers(token),
    )
    assert expire.status_code == 200, expire.text
    assert expire.json() == {"closed_positions": 1}
    assert backfill_calls == [{"date_from": date(2026, 3, 20)}]

    positions = (
        await client.get("/api/v1/positions", params={"only_open": "false"}, headers=_auth_headers(token))
    ).json()
    turbo_position = next(p for p in positions if p["asset_id"] == turbo)
    assert turbo_position["quantity"] == "0.0000000000"
    assert turbo_position["realized_pl"] == "-25.00"

    after = (await client.get("/api/v1/corporate-actions/suggestions", headers=_auth_headers(token))).json()
    assert after["expirations"] == []
    again = await client.post(
        "/api/v1/corporate-actions/expire",
        json={"asset_id": turbo, "expiry_date": "2026-03-20"},
        headers=_auth_headers(token),
    )
    assert again.status_code == 400

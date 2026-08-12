"""Test del report builder Google Sheets (milestone 10): verifica che il
contenuto assemblato rifletta i dati reali passando dai service esistenti
(analytics.py/portfolio_analytics.py), non query duplicate, e che il tab
Portfolio sia incluso/omesso correttamente.
"""
import uuid
from datetime import date

from httpx import AsyncClient

from app.db.rls import rls_session
from app.integrations.google.report_builder import ReportOptions, build_report


async def _register(client: AsyncClient, email: str) -> tuple[str, uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    body = response.json()
    return body["access_token"], uuid.UUID(body["user"]["id"]), uuid.UUID(body["user"]["workspace_id"])


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_transaction(client: AsyncClient, token: str, account_id: str, **overrides) -> None:
    payload = {
        "financial_account_id": account_id,
        "transaction_date": "2026-05-15",
        "description_raw": "Movimento",
        "amount": "-10.00",
        "currency": "EUR",
        "direction": "debit",
        "transaction_type": "expense",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/transactions", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text


async def test_build_report_reflects_real_transactions_without_portfolio_sheet(client):
    token, user_id, workspace_id = await _register(client, "report-builder@example.com")
    account_id = await _create_account(client, token)
    await _create_transaction(
        client, token, account_id, amount="2000.00", direction="credit", transaction_type="income"
    )
    await _create_transaction(
        client, token, account_id,
        amount="-50.00", direction="debit", transaction_type="expense",
        description_raw="Supermercato",
    )

    options = ReportOptions(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))
    async with rls_session(user_id) as db:
        content = await build_report(db, workspace_id, options)

    # Nessuna posizione nel workspace: il tab Portfolio non viene creato.
    assert content.sheet_titles == ["Riepilogo", "Transazioni", "Entrate per Categoria", "Uscite per Categoria"]

    transazioni_range = next(r for r in content.value_ranges if r["range"].startswith("Transazioni"))
    descriptions = [row[2] for row in transazioni_range["values"][1:]]
    assert "Supermercato" in descriptions

    # Il grafico a torta/barre e la formattazione bold sono stati generati.
    assert len(content.requests) > 0


async def test_build_report_empty_category_shows_fallback_message_not_broken_chart(client):
    token, user_id, workspace_id = await _register(client, "report-builder-empty@example.com")
    account_id = await _create_account(client, token)
    await _create_transaction(
        client, token, account_id, amount="2000.00", direction="credit", transaction_type="income"
    )
    # Nessuna uscita nel periodo.

    options = ReportOptions(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))
    async with rls_session(user_id) as db:
        content = await build_report(db, workspace_id, options)

    uscite_range = next(r for r in content.value_ranges if r["range"].startswith("Uscite"))
    assert uscite_range["values"] == [
        ["Categoria", "Totale", "Quota", "N. transazioni"],
        ["Nessun movimento nel periodo selezionato."],
    ]


async def test_build_report_can_force_portfolio_sheet_even_without_holdings(client):
    token, user_id, workspace_id = await _register(client, "report-builder-portfolio@example.com")

    options = ReportOptions(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31), include_portfolio=True)
    async with rls_session(user_id) as db:
        content = await build_report(db, workspace_id, options)

    assert "Portfolio" in content.sheet_titles


async def test_build_report_without_charts_produces_no_chart_requests(client):
    token, user_id, workspace_id = await _register(client, "report-builder-nocharts@example.com")
    account_id = await _create_account(client, token)
    await _create_transaction(
        client, token, account_id, amount="-50.00", direction="debit", transaction_type="expense"
    )

    options = ReportOptions(date_from=date(2026, 5, 1), date_to=date(2026, 5, 31), include_charts=False)
    async with rls_session(user_id) as db:
        content = await build_report(db, workspace_id, options)

    assert all("addChart" not in r for r in content.requests)

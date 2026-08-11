"""Test API della mappatura tipi transazione configurabile per parser
(milestone 09.5). Registrazione/conto via API (come gli altri test API);
Import/Transaction inseriti direttamente via DB (nessun endpoint crea una
transazione con `import_id`/`source_type_raw` — sono popolati solo dal
worker che elabora un vero PDF, sproporzionato da rifare qui solo per
testare questo strato, stesso principio di test_transaction_type_mapping_service.py).
"""
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import text

from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.transaction import Transaction

_TR_BANK_ID = uuid.UUID("6bb6eb78-276d-4b2f-ac63-8eef2c57d307")
_TR_BANK_PARSER_ID = uuid.UUID("1f6a5b19-3b40-4b3e-9a7b-2e0d6f1c9a44")
_PARSER_TYPE = "trade_republic_pdf"


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _workspace_and_user(client: AsyncClient, token: str) -> tuple[uuid.UUID, uuid.UUID]:
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    body = me.json()
    return uuid.UUID(body["workspace_id"]), uuid.UUID(body["id"])


async def _seed_bonifico_transactions(workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    async with rls_session(user_id) as db:
        # Conto Trade Republic (nessun endpoint dedicato serve qui: si crea
        # la riga direttamente, stesso principio del resto del file).
        account_id = (
            await db.execute(
                text(
                    "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                    "VALUES (:w, 'Trade Republic', 'brokerage', 'EUR') RETURNING id"
                ),
                {"w": str(workspace_id)},
            )
        ).scalar_one()

        import_row = Import(
            workspace_id=workspace_id,
            financial_account_id=account_id,
            created_by_user_id=user_id,
            status="completed",
            filename="estratto.pdf",
            file_hash=uuid.uuid4().hex,
            file_size=1000,
            file_type="pdf",
            bank_id=_TR_BANK_ID,
            bank_parser_id=_TR_BANK_PARSER_ID,
        )
        db.add(import_row)
        await db.flush()

        db.add(
            Transaction(
                workspace_id=workspace_id,
                financial_account_id=account_id,
                import_id=import_row.id,
                transaction_date=date(2026, 1, 1),
                description_raw="bonifico in entrata",
                amount="100.00",
                currency="EUR",
                direction="credit",
                transaction_type="income",
                source_type_raw="Bonifico",
            )
        )
        db.add(
            Transaction(
                workspace_id=workspace_id,
                financial_account_id=account_id,
                import_id=import_row.id,
                transaction_date=date(2026, 1, 2),
                description_raw="bonifico in uscita, corretto a mano",
                amount="-50.00",
                currency="EUR",
                direction="debit",
                transaction_type="fee",  # non e' il default (expense): simula una correzione manuale
                source_type_raw="Bonifico",
            )
        )
        await db.commit()


async def test_no_parsers_used_when_no_pdf_import_exists(client):
    token = await _register(client, "ttm-api-noparsers@example.com")
    response = await client.get("/api/v1/settings/transaction-types/parsers", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() == []


async def test_labels_and_upsert_with_retroactive_reapply(client):
    token = await _register(client, "ttm-api-flow@example.com")
    workspace_id, user_id = await _workspace_and_user(client, token)
    await _seed_bonifico_transactions(workspace_id, user_id)

    parsers = await client.get("/api/v1/settings/transaction-types/parsers", headers=_auth_headers(token))
    assert parsers.json() == [_PARSER_TYPE]

    labels = await client.get(
        f"/api/v1/settings/transaction-types/{_PARSER_TYPE}/labels", headers=_auth_headers(token)
    )
    assert labels.status_code == 200
    body = labels.json()
    assert len(body) == 1
    assert body[0]["source_type_raw"] == "Bonifico"
    assert body[0]["total_count"] == 2
    assert body[0]["override"] is None

    upsert = await client.put(
        f"/api/v1/settings/transaction-types/{_PARSER_TYPE}/labels/Bonifico",
        json={"transaction_type": "transfer"},
        headers=_auth_headers(token),
    )
    assert upsert.status_code == 200, upsert.text
    result = upsert.json()
    assert result["transaction_type"] == "transfer"
    assert result["reapply"]["updated"] == 1  # solo quella ancora al default (income)
    assert result["reapply"]["skipped"] == 1  # quella corretta a mano (fee) resta intatta

    labels_after = await client.get(
        f"/api/v1/settings/transaction-types/{_PARSER_TYPE}/labels", headers=_auth_headers(token)
    )
    assert labels_after.json()[0]["override"] == "transfer"


async def test_delete_mapping_reverts_to_default_returns_404_if_missing(client):
    token = await _register(client, "ttm-api-delete@example.com")
    workspace_id, user_id = await _workspace_and_user(client, token)
    await _seed_bonifico_transactions(workspace_id, user_id)

    missing = await client.delete(
        f"/api/v1/settings/transaction-types/{_PARSER_TYPE}/labels/Bonifico", headers=_auth_headers(token)
    )
    assert missing.status_code == 404

    await client.put(
        f"/api/v1/settings/transaction-types/{_PARSER_TYPE}/labels/Bonifico",
        json={"transaction_type": "transfer"},
        headers=_auth_headers(token),
    )
    deleted = await client.delete(
        f"/api/v1/settings/transaction-types/{_PARSER_TYPE}/labels/Bonifico", headers=_auth_headers(token)
    )
    assert deleted.status_code == 204


async def test_upsert_rejects_unknown_transaction_type(client):
    token = await _register(client, "ttm-api-badtype@example.com")
    workspace_id, user_id = await _workspace_and_user(client, token)
    await _seed_bonifico_transactions(workspace_id, user_id)

    response = await client.put(
        f"/api/v1/settings/transaction-types/{_PARSER_TYPE}/labels/Bonifico",
        json={"transaction_type": "not_a_real_type"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422

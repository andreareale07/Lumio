"""Verifica che i punti di aggancio dell'audit log (milestone 11, SPEC §59)
scrivano davvero una riga per l'evento giusto — a differenza di
`test_rls_audit_log.py` (isolamento RLS puro), qui si passa dall'API reale
e si legge il risultato con una query diretta (nessun endpoint di
consultazione esiste ancora in questa milestone, deciso con l'utente)."""
import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.db.base import async_session_factory
from app.worker.jobs.import_job import import_job

CSV_SAMPLE = (
    "data,descrizione,importo\n"
    "2026-01-15,Supermercato Lidl,-42.50\n"
    "2026-01-16,Stipendio,1500.00\n"
)


async def _register(client: AsyncClient, email: str) -> tuple[str, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    body = response.json()
    return body["access_token"], uuid.UUID(body["user"]["id"])


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _audit_events(user_id: uuid.UUID, event_type: str) -> list[dict]:
    async with async_session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        result = await session.execute(
            text(
                "SELECT entity_type, entity_id, metadata FROM audit_log "
                "WHERE event_type = :event_type ORDER BY created_at"
            ),
            {"event_type": event_type},
        )
        return [dict(row._mapping) for row in result]


async def test_login_writes_audit_event(client):
    _token, user_id = await _register(client, "audit-login@example.com")
    # register() stesso non e' nell'elenco SPEC §59 (solo LOGIN): nessuna riga
    # dopo la sola registrazione.
    assert await _audit_events(user_id, "LOGIN") == []

    login = await client.post(
        "/api/v1/auth/login", json={"email": "audit-login@example.com", "password": "correct-password-123"}
    )
    assert login.status_code == 200

    events = await _audit_events(user_id, "LOGIN")
    assert len(events) == 1
    assert events[0]["entity_type"] == "user"
    assert events[0]["entity_id"] == user_id


async def test_category_crud_writes_audit_events(client):
    token, user_id = await _register(client, "audit-category@example.com")

    create = await client.post(
        "/api/v1/categories", json={"name": "Hobby", "code": "hobby"}, headers=_auth_headers(token)
    )
    category_id = uuid.UUID(create.json()["id"])

    await client.patch(
        f"/api/v1/categories/{category_id}", json={"name": "Hobby e tempo libero"}, headers=_auth_headers(token)
    )
    await client.delete(f"/api/v1/categories/{category_id}", headers=_auth_headers(token))

    events = await _audit_events(user_id, "CATEGORY_CHANGED")
    actions = [e["metadata"]["action"] for e in events]
    assert actions == ["created", "updated", "deleted"]
    assert all(e["entity_id"] == category_id for e in events)


async def test_rule_create_and_update_write_audit_events(client):
    token, user_id = await _register(client, "audit-rule@example.com")
    categories = await client.get("/api/v1/categories", headers=_auth_headers(token))
    category_id = categories.json()[0]["id"]

    create = await client.post(
        "/api/v1/rules",
        json={"name": "Lidl", "field": "description", "operator": "contains", "value": "Lidl",
              "category_id": category_id},
        headers=_auth_headers(token),
    )
    rule_id = uuid.UUID(create.json()["id"])
    assert len(await _audit_events(user_id, "RULE_CREATED")) == 1

    await client.patch(f"/api/v1/rules/{rule_id}", json={"name": "Lidl supermercato"}, headers=_auth_headers(token))
    updated = await _audit_events(user_id, "RULE_UPDATED")
    assert len(updated) == 1
    assert updated[0]["entity_id"] == rule_id


async def test_transaction_update_writes_audit_event_only_when_fields_change(client):
    token, user_id = await _register(client, "audit-txn@example.com")
    account = await client.post(
        "/api/v1/accounts", json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]
    created = await client.post(
        "/api/v1/transactions",
        json={
            "financial_account_id": account_id, "transaction_date": "2026-01-01",
            "description_raw": "Spesa", "amount": "-10.00", "currency": "EUR", "direction": "debit",
            "transaction_type": "expense",
        },
        headers=_auth_headers(token),
    )
    transaction_id = uuid.UUID(created.json()["id"])

    # PATCH senza campi (corpo vuoto): nessun aggiornamento reale, nessun evento.
    await client.patch(f"/api/v1/transactions/{transaction_id}", json={}, headers=_auth_headers(token))
    assert await _audit_events(user_id, "TRANSACTION_UPDATED") == []

    await client.patch(
        f"/api/v1/transactions/{transaction_id}", json={"merchant": "Negozio corretto"},
        headers=_auth_headers(token),
    )
    events = await _audit_events(user_id, "TRANSACTION_UPDATED")
    assert len(events) == 1
    assert events[0]["entity_id"] == transaction_id


async def test_ai_activate_and_deactivate_write_audit_events(client):
    token, user_id = await _register(client, "audit-ai@example.com")
    create = await client.post(
        "/api/v1/settings/ai/profiles",
        json={"name": "Locale", "provider": "ollama", "endpoint": "http://ollama:11434", "model": "llama3"},
        headers=_auth_headers(token),
    )
    profile_id = uuid.UUID(create.json()["id"])

    await client.post(f"/api/v1/settings/ai/profiles/{profile_id}/activate", headers=_auth_headers(token))
    activated = await _audit_events(user_id, "AI_PROVIDER_CHANGED")
    assert len(activated) == 1
    assert activated[0]["metadata"]["action"] == "activated"

    await client.post("/api/v1/settings/ai/deactivate", headers=_auth_headers(token))
    events = await _audit_events(user_id, "AI_PROVIDER_CHANGED")
    assert len(events) == 2
    assert events[1]["metadata"]["action"] == "deactivated"


async def test_import_created_and_completed_write_audit_events(client):
    token, user_id = await _register(client, "audit-import@example.com")
    account = await client.post(
        "/api/v1/accounts", json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    account_id = account.json()["id"]

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    created = await _audit_events(user_id, "IMPORT_CREATED")
    assert len(created) == 1
    assert created[0]["entity_id"] == uuid.UUID(import_id)
    assert await _audit_events(user_id, "IMPORT_COMPLETED") == []

    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    await import_job(None, import_id, str(user_id))

    completed = await _audit_events(user_id, "IMPORT_COMPLETED")
    assert len(completed) == 1
    assert completed[0]["entity_id"] == uuid.UUID(import_id)
    assert completed[0]["metadata"]["transactions_imported"] == 2

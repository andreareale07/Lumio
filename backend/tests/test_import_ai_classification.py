"""Integrazione worker import + AI (milestone 07, SPEC §28: Rules -> AI).
Stesso schema di test_classifications.py::test_import_classifies_matching_
transactions_via_rule, ma senza alcuna regola attiva: la riga "ACME
STREAMING" viene classificata dal provider "custom" (mockato via
pytest-httpx, nessuna rete reale), la riga "ACME GENERIC MERCHANT" resta non
classificata perche' il provider risponde con `category_code: null`.

Merchant volutamente fittizi (non "Netflix"/"Farmacia" come nelle versioni
precedenti di questo test): devono restare NON classificabili da nessun
livello deterministico della pipeline (rules_engine/type_map/catalogo di
sistema, vedi app/services/classification_pipeline.py), altrimenti non
arriverebbero mai all'AI e questi test — che vogliono esercitare proprio il
job AI — non testerebbero piu' nulla.

Rework "disaccoppiamento AI": la classificazione non avviene piu' dentro
`import_job` (vedi worker/jobs/import_job.py) ma in un job separato,
`classify_import_transactions_job` — nei test, senza un vero worker arq in
ascolto, va invocato esplicitamente dopo `import_job`, stesso schema gia'
usato per `import_job` stesso in questi test.
"""
import json

import httpx
from httpx import AsyncClient

from app.worker.jobs.ai_classification_job import classify_import_transactions_job
from app.worker.jobs.import_job import import_job

CSV_SAMPLE = (
    "data,descrizione,importo\n"
    "2026-01-15,Pagamento ACME STREAMING SERVICE,-12.99\n"
    "2026-01-16,Pagamento ACME GENERIC MERCHANT,-8.00\n"
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


async def _category_id(client: AsyncClient, token: str, code: str) -> str:
    response = await client.get("/api/v1/categories", headers=_auth_headers(token))
    return next(c["id"] for c in response.json() if c["code"] == code)


def _custom_completion_callback(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    # Rework prompt AI: system e user sono ora due messaggi separati (prima
    # un unico messaggio) — la descrizione della transazione e' nello user,
    # non nel system, quindi va cercata in tutti i messaggi, non solo nel
    # primo.
    prompt = " ".join(m["content"] for m in body["messages"])
    if "ACME STREAMING" in prompt:
        content = '{"category_code": "abbonamenti.streaming", "confidence": 0.92, "reason": "streaming"}'
    else:
        content = '{"category_code": null, "confidence": 0.2}'
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_import_classifies_unmatched_transaction_via_ai(client, httpx_mock):
    token = await _register(client, "ai-import@example.com")
    account_id = await _create_account(client, token)
    streaming_category_id = await _category_id(client, token, "abbonamenti.streaming")

    create_response = await client.post(
        "/api/v1/settings/ai/profiles",
        json={
            "name": "Server locale",
            "provider": "custom",
            "endpoint": "http://fake-ai.local/v1",
            "model": "local-model",
        },
        headers=_auth_headers(token),
    )
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]
    activate_response = await client.post(
        f"/api/v1/settings/ai/profiles/{profile_id}/activate", headers=_auth_headers(token)
    )
    assert activate_response.status_code == 200

    httpx_mock.add_callback(
        _custom_completion_callback, url="http://fake-ai.local/v1/chat/completions"
    )

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    user_id = me.json()["id"]
    await import_job(None, import_id, user_id)

    # Rework "disaccoppiamento AI": subito dopo import_job, le transazioni
    # esistono ma nessuna e' ancora classificata dall'AI — l'import stesso e'
    # gia' 'completed', in attesa del job separato (vedi commento in testa al
    # file).
    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["status"] == "completed"
    assert detail.json()["ai_classification_status"] == "pending"
    assert detail.json()["ai_transactions_total"] == 2  # nessuna regola attiva, entrambe le righe

    await classify_import_transactions_job(None, import_id, user_id)

    detail_after = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail_after.json()["ai_classification_status"] == "completed"
    # 1, non 2: `ai_transactions_classified` conta le classificazioni
    # RIUSCITE, non i tentativi (fix del bug riportato dall'utente su un
    # provider spento a meta' import — vedi ai_classification_job.py). La
    # riga "ACME GENERIC MERCHANT" e' stata tentata ma il provider ha
    # risposto `category_code: null`: nessun errore, ma nemmeno una
    # classificazione.
    assert detail_after.json()["ai_transactions_classified"] == 1

    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    rows = transactions.json()
    streaming_row = next(r for r in rows if "ACME STREAMING" in r["description_raw"])
    generic_row = next(r for r in rows if "ACME GENERIC" in r["description_raw"])

    assert streaming_row["category_id"] == streaming_category_id
    assert generic_row["category_id"] is None

    history = await client.get(
        f"/api/v1/transactions/{streaming_row['id']}/classifications", headers=_auth_headers(token)
    )
    entries = history.json()
    assert len(entries) == 1
    assert entries[0]["method"] == "ai"
    assert entries[0]["provider"] == "custom"
    assert entries[0]["model"] == "local-model"
    assert entries[0]["category_id"] == streaming_category_id
    # confidence 0.92 dichiarata, merchant riconosciuto (rework pipeline:
    # merchant_extraction.py risveglia Transaction.merchant, mai valorizzato
    # prima) -> nessuno sconto di confidence (app/services/confidence.py)
    assert entries[0]["score"] == "0.92"

    generic_history = await client.get(
        f"/api/v1/transactions/{generic_row['id']}/classifications", headers=_auth_headers(token)
    )
    assert generic_history.json() == []


async def test_ai_prompt_offers_only_categories_matching_transaction_kind(client, httpx_mock):
    # Rework prompt AI: una spesa (direction=debit) non deve mai vedersi
    # offrire categorie di kind "income" — dimezza le opzioni e con esse le
    # occasioni di sbagliare, invece della tassonomia intera per ogni riga.
    token = await _register(client, "ai-kind-filter@example.com")
    account_id = await _create_account(client, token)

    create_response = await client.post(
        "/api/v1/settings/ai/profiles",
        json={
            "name": "Server locale",
            "provider": "custom",
            "endpoint": "http://fake-ai-kind.local/v1",
            "model": "local-model",
        },
        headers=_auth_headers(token),
    )
    profile_id = create_response.json()["id"]
    await client.post(f"/api/v1/settings/ai/profiles/{profile_id}/activate", headers=_auth_headers(token))

    captured_prompts: list[str] = []

    def _capture_callback(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured_prompts.append(" ".join(m["content"] for m in body["messages"]))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"category_code": null, "confidence": 0.1}'}}]}
        )

    httpx_mock.add_callback(_capture_callback, url="http://fake-ai-kind.local/v1/chat/completions")

    csv_content = "data,descrizione,importo\n2026-01-15,Pagamento ACME MISTERO SRL,-25.00\n"
    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", csv_content.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]
    await client.post(
        f"/api/v1/imports/{import_id}/confirm", json={"mapping": suggested_mapping}, headers=_auth_headers(token)
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])
    await classify_import_transactions_job(None, import_id, me.json()["id"])

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # Categoria di spesa: deve comparire.
    assert "trasporti.carburante" in prompt
    # Categorie di entrata/trasferimento/investimento: non devono comparire
    # per una riga debit/expense.
    assert "entrate.stipendio" not in prompt
    assert "trasferimenti.giroconto" not in prompt
    assert "investimenti.acquisto_titoli" not in prompt


async def test_import_skips_ai_when_provider_is_none(client, httpx_mock):
    token = await _register(client, "ai-import-disabled@example.com")
    account_id = await _create_account(client, token)

    upload = await client.post(
        "/api/v1/imports",
        data={"financial_account_id": account_id},
        files={"file": ("estratto.csv", CSV_SAMPLE.encode(), "text/csv")},
        headers=_auth_headers(token),
    )
    import_id = upload.json()["import"]["id"]
    suggested_mapping = upload.json()["preview"]["suggested_mapping"]

    await client.post(
        f"/api/v1/imports/{import_id}/confirm",
        json={"mapping": suggested_mapping},
        headers=_auth_headers(token),
    )
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    await import_job(None, import_id, me.json()["id"])

    # Nessuna richiesta HTTP verso alcun provider: httpx_mock solleverebbe
    # un errore se un test tentasse una richiesta non registrata, quindi
    # arrivare qui senza eccezioni conferma che l'AI (provider='none' di
    # default, SPEC §25) non e' mai stata invocata, e nessun job di
    # classificazione e' stato accodato.
    transactions = await client.get(
        "/api/v1/transactions", params={"financial_account_id": account_id}, headers=_auth_headers(token)
    )
    rows = transactions.json()
    assert all(r["category_id"] is None for r in rows)

    detail = await client.get(f"/api/v1/imports/{import_id}", headers=_auth_headers(token))
    assert detail.json()["ai_classification_status"] == "skipped"
    assert detail.json()["ai_transactions_total"] == 0

"""API delle regole con condizioni multiple, anteprima di impatto e
applicazione di una regola ai movimenti esistenti."""
from httpx import AsyncClient

from app.worker.jobs.reclassification_job import reclassify_workspace_job


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _category(client: AsyncClient, token: str, code: str) -> str:
    response = await client.get("/api/v1/categories", headers=_auth(token))
    return next(c["id"] for c in response.json() if c["code"] == code)


async def _account(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": "Conto", "account_type": "checking", "currency": "EUR"},
        headers=_auth(token),
    )
    return response.json()["id"]


async def _transaction(client, token, account_id, description, *, amount="-10.00", category_id=None) -> dict:
    payload = {
        "financial_account_id": account_id,
        "transaction_date": "2026-03-01",
        "description_raw": description,
        "amount": amount,
        "currency": "EUR",
        "direction": "debit",
        "transaction_type": "expense",
    }
    if category_id:
        payload["category_id"] = category_id
    response = await client.post("/api/v1/transactions", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def _contains(value: str) -> dict:
    return {"field": "description", "operator": "contains", "value": value}


def _amount(min_value=None, max_value=None) -> dict:
    return {"field": "amount", "operator": "between", "min": min_value, "max": max_value}


async def _create_rule(client, token, category_id, conditions, **extra) -> dict:
    response = await client.post(
        "/api/v1/rules",
        json={"name": "Regola", "conditions": conditions, "category_id": category_id, **extra},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_rule_with_text_and_amount_conditions(client):
    token = await _register(client, "cond-create@example.com")
    category_id = await _category(client, token, "abbonamenti.streaming")

    rule = await _create_rule(client, token, category_id, [_contains("rata mutuo"), _amount("450", "520")])

    assert rule["match_mode"] == "all"
    assert rule["conditions"][0] == _contains("rata mutuo")
    assert rule["conditions"][1]["field"] == "amount"
    assert float(rule["conditions"][1]["min"]) == 450 and float(rule["conditions"][1]["max"]) == 520
    listed = await client.get("/api/v1/rules", headers=_auth(token))
    assert listed.json()[0]["conditions"] == rule["conditions"]


async def test_single_condition_shorthand_is_still_accepted(client):
    token = await _register(client, "cond-legacy@example.com")
    category_id = await _category(client, token, "abbonamenti.streaming")
    response = await client.post(
        "/api/v1/rules",
        json={"name": "Netflix", "field": "description", "operator": "contains", "value": "netflix", "category_id": category_id},
        headers=_auth(token),
    )
    assert response.status_code == 201
    assert response.json()["conditions"] == [_contains("netflix")]


async def test_invalid_conditions_are_rejected(client):
    token = await _register(client, "cond-invalid@example.com")
    category_id = await _category(client, token, "abbonamenti.streaming")
    bad_conditions = [
        [],
        [_contains("x")] * 11,
        [{"field": "description", "operator": "regex", "value": "(a+)+$"}],
        [{"field": "description", "operator": "regex", "value": "[unterminated"}],
        [_amount(None, None)],
        [_amount("600", "100")],
        [_amount("-5", "10")],
        [{"field": "description", "operator": "merchant_equals", "value": "x"}],
    ]
    for conditions in bad_conditions:
        response = await client.post(
            "/api/v1/rules",
            json={"name": "x", "conditions": conditions, "category_id": category_id},
            headers=_auth(token),
        )
        assert response.status_code == 422, conditions


async def test_patch_replaces_conditions_and_match_mode(client):
    token = await _register(client, "cond-patch@example.com")
    category_id = await _category(client, token, "abbonamenti.streaming")
    rule = await _create_rule(client, token, category_id, [_contains("netflix")])

    response = await client.patch(
        f"/api/v1/rules/{rule['id']}",
        json={"conditions": [_contains("netflix"), _contains("spotify")], "match_mode": "any"},
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["match_mode"] == "any"
    assert len(response.json()["conditions"]) == 2


async def test_manual_transaction_is_classified_by_an_amount_rule(client):
    token = await _register(client, "cond-amount@example.com")
    account_id = await _account(client, token)
    category_id = await _category(client, token, "abbonamenti.streaming")
    await _create_rule(client, token, category_id, [_contains("zxq rata"), _amount("450", "520")])

    inside = await _transaction(client, token, account_id, "Zxq rata alfa", amount="-487.30")
    outside = await _transaction(client, token, account_id, "Zxq rata beta", amount="-900.00")

    assert inside["category_id"] == category_id
    assert outside["category_id"] is None


async def test_preview_splits_matches_into_change_ok_and_protected(client):
    token = await _register(client, "cond-preview@example.com")
    account_id = await _account(client, token)
    target = await _category(client, token, "abbonamenti.streaming")
    other = await _category(client, token, "abbonamenti.software")

    await _transaction(client, token, account_id, "Zxq rata gennaio")  # cambierebbe
    await _transaction(client, token, account_id, "Zxq rata febbraio", category_id=target)  # gia' giusto
    await _transaction(client, token, account_id, "Zxq rata marzo", category_id=other)  # protetto
    await _transaction(client, token, account_id, "Cena fuori")  # non combacia

    response = await client.post(
        "/api/v1/rules/preview",
        json={"conditions": [_contains("zxq rata")], "category_id": target},
        headers=_auth(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["would_change"], body["already_correct"], body["protected"], body["total"]) == (1, 1, 1, 3)
    assert body["recategorized"] == 0  # il movimento che cambierebbe e' senza categoria
    assert len(body["items"]) == 3 and body["truncated"] is False

    only_changes = await client.post(
        "/api/v1/rules/preview",
        json={"conditions": [_contains("zxq rata")], "category_id": target, "group": "change"},
        headers=_auth(token),
    )
    items = only_changes.json()["items"]
    assert [i["description"] for i in items] == ["Zxq rata gennaio"]
    start, end = items[0]["spans"][0]
    assert items[0]["description"][start:end].lower() == "zxq rata"


async def test_preview_rejects_unknown_category_and_other_workspace_category(client):
    token = await _register(client, "cond-preview-a@example.com")
    other_token = await _register(client, "cond-preview-b@example.com")
    foreign = await client.post(
        "/api/v1/categories", json={"name": "Privata", "code": "privata_b"}, headers=_auth(other_token)
    )
    for category_id in ("00000000-0000-0000-0000-000000000001", foreign.json()["id"]):
        response = await client.post(
            "/api/v1/rules/preview",
            json={"conditions": [_contains("x")], "category_id": category_id},
            headers=_auth(token),
        )
        assert response.status_code == 400


async def test_preview_requires_authentication(client):
    response = await client.post(
        "/api/v1/rules/preview",
        json={"conditions": [_contains("x")], "category_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code in (401, 403)


async def test_applying_a_rule_reclassifies_only_its_matches(client):
    token = await _register(client, "cond-apply@example.com")
    account_id = await _account(client, token)
    target = await _category(client, token, "abbonamenti.streaming")
    other = await _category(client, token, "abbonamenti.software")

    matching = await _transaction(client, token, account_id, "Zxq rata alfa")
    manual = await _transaction(client, token, account_id, "Zxq rata beta", category_id=other)
    unrelated = await _transaction(client, token, account_id, "Qualcosa di generico zxv")
    rule = await _create_rule(client, token, target, [_contains("zxq rata")])

    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    workspace_id = (
        await client.post("/api/v1/categories", json={"name": "WS", "code": "ws_probe_apply"}, headers=_auth(token))
    ).json()["workspace_id"]
    await reclassify_workspace_job(None, workspace_id, me.json()["id"], "all_except_manual", False, rule["id"])

    async def current(transaction_id):
        response = await client.get(f"/api/v1/transactions/{transaction_id}", headers=_auth(token))
        return response.json()["category_id"]

    assert await current(matching["id"]) == target
    assert await current(manual["id"]) == other  # la correzione manuale non si tocca
    assert await current(unrelated["id"]) is None


async def test_reclassify_with_unknown_rule_is_404(client):
    token = await _register(client, "cond-apply-404@example.com")
    response = await client.post(
        "/api/v1/classification/reclassify",
        json={"scope": "all_except_manual", "rule_id": "00000000-0000-0000-0000-000000000009"},
        headers=_auth(token),
    )
    assert response.status_code == 404

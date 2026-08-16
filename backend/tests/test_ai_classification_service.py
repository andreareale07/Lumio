import uuid

from httpx import AsyncClient

from app.db.rls import rls_session
from app.services.ai_classification import kinds_for_transaction, load_category_options


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _current_workspace_id(client: AsyncClient, token: str) -> uuid.UUID:
    # Nessun endpoint /workspaces/current: una categoria custom appena
    # creata riporta il proprio workspace_id nella risposta, stesso
    # meccanismo indiretto gia' usato da altri test di questo file.
    response = await client.post(
        "/api/v1/categories",
        json={"name": "WS Probe", "code": f"ws_probe_{uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(token),
    )
    return uuid.UUID(response.json()["workspace_id"])


def test_kinds_for_transaction_debit_offers_expense_and_neutral():
    assert kinds_for_transaction("debit", "expense") == frozenset({"expense", "neutral"})


def test_kinds_for_transaction_credit_offers_income_and_neutral():
    assert kinds_for_transaction("credit", "income") == frozenset({"income", "neutral"})


def test_kinds_for_transaction_refund_always_offers_expense():
    # Un rimborso e' la negazione di una spesa (es. reso Amazon): deve
    # risolvere sulla stessa categoria della spesa originale, non su
    # "entrate" — altrimenti la spesa vera sparirebbe dalle analytics.
    assert kinds_for_transaction("credit", "refund") == frozenset({"expense", "neutral"})
    assert kinds_for_transaction("debit", "refund") == frozenset({"expense", "neutral"})


def test_kinds_for_transaction_adjustment_stays_open_both_sides():
    assert kinds_for_transaction("debit", "adjustment") == frozenset({"expense", "income", "neutral"})


async def test_load_category_options_filters_by_kind(client):
    token = await _register(client, "ai-kinds-filter@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = await _current_workspace_id(client, token)
    user_id = uuid.UUID(me.json()["id"])

    async with rls_session(user_id) as db:
        expense_only = await load_category_options(db, workspace_id, kinds=frozenset({"expense"}))
        income_only = await load_category_options(db, workspace_id, kinds=frozenset({"income"}))

    assert all(c.kind == "expense" for c in expense_only)
    assert all(c.kind == "income" for c in income_only)
    # Le due liste non si sovrappongono (nessuna categoria e' sia expense
    # che income).
    assert {c.id for c in expense_only}.isdisjoint({c.id for c in income_only})


async def test_load_category_options_leaves_only_excludes_roots_with_children(client):
    token = await _register(client, "ai-leaves-only@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = await _current_workspace_id(client, token)
    user_id = uuid.UUID(me.json()["id"])

    categories_resp = await client.get("/api/v1/categories", headers=_auth_headers(token))
    root_codes_with_children = {
        c["code"] for c in categories_resp.json()
        if c["parent_id"] is None
        and any(o["parent_id"] == c["id"] for o in categories_resp.json())
    }
    assert root_codes_with_children, "fixture di test inconsistente: nessuna radice con figli trovata"

    async with rls_session(user_id) as db:
        leaves_only = await load_category_options(db, workspace_id, leaves_only=True)
        all_options = await load_category_options(db, workspace_id, leaves_only=False)

    leaves_only_codes = {c.code for c in leaves_only}
    assert not (root_codes_with_children & leaves_only_codes)
    assert len(all_options) > len(leaves_only)


async def test_load_category_options_populates_parent_and_hint(client):
    token = await _register(client, "ai-parent-hint@example.com")
    me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
    workspace_id = await _current_workspace_id(client, token)
    user_id = uuid.UUID(me.json()["id"])

    async with rls_session(user_id) as db:
        options = await load_category_options(db, workspace_id)

    fuel = next(o for o in options if o.code == "trasporti.carburante")
    assert fuel.parent_code == "trasporti"
    assert fuel.parent_name == "Trasporti"
    assert fuel.hint is not None and "benzina" in fuel.hint

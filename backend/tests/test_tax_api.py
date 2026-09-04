"""API fiscale (SPEC_TAX_REGIME.md FETTA 1) — scenario Trade Republic
(un conto, due periodi di regime) + validazioni end-to-end."""
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, token: str, name: str = "Trade Republic") -> str:
    response = await client.post(
        "/api/v1/accounts",
        json={"name": name, "account_type": "brokerage", "currency": "EUR"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_asset(client: AsyncClient, token: str, **overrides) -> str:
    payload = {"name": "iShares Core MSCI World UCITS ETF", "asset_type": "etf", "currency": "EUR"}
    payload.update(overrides)
    response = await client.post("/api/v1/assets", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201
    return response.json()["id"]


# --- pagina regole -------------------------------------------------------------


async def test_ruleset_reflection_every_dataclass_field_is_served(client):
    token = await _register(client, "tax-ruleset@example.com")
    response = await client.get(
        "/api/v1/tax/ruleset", params={"on": "2020-01-01"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "IT-2014-07"
    assert body["treatments"]
    treatment = body["treatments"][0]
    for field in (
        "asset_class", "event_kind", "gain_category", "loss_category", "status",
        "rate", "taxable_coefficient", "legal_reference", "assumption", "assumption_note",
    ):
        assert field in treatment
    assert body["carry_forward"]["assumption"] is True
    assert "FISCAL ASSUMPTION REQUIRING VALIDATION" in body["carry_forward"]["assumption_note"]


async def test_ruleset_before_2000_returns_400_not_500(client):
    token = await _register(client, "tax-ruleset-early@example.com")
    response = await client.get(
        "/api/v1/tax/ruleset", params={"on": "1999-12-31"}, headers=_auth_headers(token)
    )
    assert response.status_code == 400


# --- scenario Trade Republic: due periodi di regime ---------------------------


async def test_trade_republic_two_regime_periods_resolve_correctly(client):
    token = await _register(client, "tax-tr@example.com")
    account_id = await _create_account(client, token)

    create_1 = await client.post(
        f"/api/v1/tax/accounts/{account_id}/regimes",
        json={"regime_code": "dichiarativo", "effective_from": "2020-01-01"},
        headers=_auth_headers(token),
    )
    assert create_1.status_code == 201

    create_2 = await client.post(
        f"/api/v1/tax/accounts/{account_id}/regimes",
        json={"regime_code": "amministrato", "effective_from": "2022-06-01"},
        headers=_auth_headers(token),
    )
    assert create_2.status_code == 201

    before = await client.get(
        "/api/v1/tax/regimes/resolve",
        params={"account_id": account_id, "on": "2021-01-01"},
        headers=_auth_headers(token),
    )
    assert before.json()["regime_code"] == "dichiarativo"

    after = await client.get(
        "/api/v1/tax/regimes/resolve",
        params={"account_id": account_id, "on": "2023-01-01"},
        headers=_auth_headers(token),
    )
    assert after.json()["regime_code"] == "amministrato"

    exactly_on_switch = await client.get(
        "/api/v1/tax/regimes/resolve",
        params={"account_id": account_id, "on": "2022-06-01"},
        headers=_auth_headers(token),
    )
    assert exactly_on_switch.json()["regime_code"] == "amministrato"


async def test_duplicate_effective_from_returns_409(client):
    token = await _register(client, "tax-tr-dup@example.com")
    account_id = await _create_account(client, token)
    first = await client.post(
        f"/api/v1/tax/accounts/{account_id}/regimes",
        json={"regime_code": "dichiarativo", "effective_from": "2020-01-01"},
        headers=_auth_headers(token),
    )
    assert first.status_code == 201

    duplicate = await client.post(
        f"/api/v1/tax/accounts/{account_id}/regimes",
        json={"regime_code": "amministrato", "effective_from": "2020-01-01"},
        headers=_auth_headers(token),
    )
    assert duplicate.status_code == 409


async def test_regime_resolve_before_any_period_is_none(client):
    token = await _register(client, "tax-tr-none@example.com")
    account_id = await _create_account(client, token)
    await client.post(
        f"/api/v1/tax/accounts/{account_id}/regimes",
        json={"regime_code": "amministrato", "effective_from": "2022-01-01"},
        headers=_auth_headers(token),
    )
    response = await client.get(
        "/api/v1/tax/regimes/resolve",
        params={"account_id": account_id, "on": "2019-01-01"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["regime_code"] is None


async def test_cross_workspace_regime_period_returns_404(client):
    token_a = await _register(client, "tax-cross-a@example.com")
    token_b = await _register(client, "tax-cross-b@example.com")
    account_a = await _create_account(client, token_a)

    response = await client.get(
        f"/api/v1/tax/accounts/{account_a}/regimes", headers=_auth_headers(token_b)
    )
    assert response.status_code == 404


# --- aperture zainetto: validazione perimetro ----------------------------------


async def test_opening_with_account_but_declarative_regime_returns_400(client):
    token = await _register(client, "tax-open-mismatch@example.com")
    account_id = await _create_account(client, token)
    await client.post(
        f"/api/v1/tax/accounts/{account_id}/regimes",
        json={"regime_code": "dichiarativo", "effective_from": "2018-01-01"},
        headers=_auth_headers(token),
    )
    response = await client.post(
        "/api/v1/tax/loss-pocket/openings",
        json={
            "financial_account_id": account_id,
            "formation_date": "2020-01-01",
            "income_category": "redditi_diversi",
            "amount": "1000.00",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


async def test_opening_aggregate_perimeter_without_account_succeeds(client):
    token = await _register(client, "tax-open-aggregate@example.com")
    response = await client.post(
        "/api/v1/tax/loss-pocket/openings",
        json={
            "financial_account_id": None,
            "formation_date": "2020-01-01",
            "income_category": "redditi_diversi",
            "amount": "1000.00",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["financial_account_id"] is None
    assert body["formed_under_ruleset_code"] == "IT-2014-07"


async def test_opening_per_account_perimeter_with_administrato_succeeds(client):
    token = await _register(client, "tax-open-admin@example.com")
    account_id = await _create_account(client, token)
    await client.post(
        f"/api/v1/tax/accounts/{account_id}/regimes",
        json={"regime_code": "amministrato", "effective_from": "2018-01-01"},
        headers=_auth_headers(token),
    )
    response = await client.post(
        "/api/v1/tax/loss-pocket/openings",
        json={
            "financial_account_id": account_id,
            "formation_date": "2020-01-01",
            "income_category": "redditi_diversi",
            "amount": "1000.00",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 201


# --- zainetto e coverage --------------------------------------------------------


async def test_loss_pocket_totals_reflect_openings(client):
    token = await _register(client, "tax-pocket@example.com")
    await client.post(
        "/api/v1/tax/loss-pocket/openings",
        json={
            "financial_account_id": None,
            "formation_date": "2022-01-01",
            "income_category": "redditi_diversi",
            "amount": "1500.00",
        },
        headers=_auth_headers(token),
    )
    response = await client.get(
        "/api/v1/tax/loss-pocket", params={"on": "2023-01-01"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["totals_by_perimeter"]["dichiarativo"] == "1500.00"
    assert body["computed_from_movements"] is False
    assert body["residence_declared"] is False


async def test_loss_pocket_after_residence_declared_flag_true(client):
    token = await _register(client, "tax-pocket-residence@example.com")
    residence = await client.put(
        "/api/v1/tax/residences/2023",
        json={"fiscal_year": 2023, "jurisdiction_code": "IT"},
        headers=_auth_headers(token),
    )
    assert residence.status_code == 200
    response = await client.get(
        "/api/v1/tax/loss-pocket", params={"on": "2023-06-01"}, headers=_auth_headers(token)
    )
    assert response.json()["residence_declared"] is True


async def test_residence_applies_forward_until_next_change(client):
    # workspace_tax_residences e' append-only per anno di decorrenza
    # (deciso dopo il rilascio di FETTA 1): una riga vale dal suo anno fino
    # al successivo cambiamento, non solo per quell'anno esatto — l'utente
    # la imposta una volta, non deve ridichiararla ogni anno.
    token = await _register(client, "tax-residence-forward@example.com")
    await client.put(
        "/api/v1/tax/residences/2018",
        json={"fiscal_year": 2018, "jurisdiction_code": "IT"},
        headers=_auth_headers(token),
    )
    far_future = await client.get(
        "/api/v1/tax/loss-pocket", params={"on": "2030-01-01"}, headers=_auth_headers(token)
    )
    assert far_future.json()["residence_declared"] is True

    before_declared = await client.get(
        "/api/v1/tax/loss-pocket", params={"on": "2017-12-31"}, headers=_auth_headers(token)
    )
    assert before_declared.json()["residence_declared"] is False


async def test_residence_multi_period_history_resolves_correct_year(client):
    # Storico multi-periodo: 2010 Italia, 2015 Svizzera, 2020 Italia di
    # nuovo — ogni intervallo si risolve dalla riga con fiscal_year piu'
    # recente <= la data richiesta.
    token = await _register(client, "tax-residence-history@example.com")
    await client.put(
        "/api/v1/tax/residences/2010",
        json={"fiscal_year": 2010, "jurisdiction_code": "IT"},
        headers=_auth_headers(token),
    )
    await client.put(
        "/api/v1/tax/residences/2020",
        json={"fiscal_year": 2020, "jurisdiction_code": "IT"},
        headers=_auth_headers(token),
    )

    early = await client.get("/api/v1/tax/ruleset", params={"on": "2012-01-01"}, headers=_auth_headers(token))
    assert early.status_code == 200

    residences = await client.get("/api/v1/tax/residences", headers=_auth_headers(token))
    assert {r["fiscal_year"] for r in residences.json()} == {2010, 2020}


# --- classificazione asset: trappola ETC ---------------------------------------


async def test_asset_classification_etf_hint_without_ucits_signal_stays_unclassified(client):
    token = await _register(client, "tax-cls-etc@example.com")
    asset_id = await _create_asset(
        client, token, name="Xetra-Gold", asset_type="etf", isin="DE000A0S9GB0"
    )
    response = await client.get(
        "/api/v1/tax/asset-classifications", params={"on": "2020-01-01"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    view = next(v for v in response.json() if v["asset_id"] == asset_id)
    assert view["asset_class"] == "unclassified"
    assert view["is_override"] is False


async def test_asset_classification_override_wins_over_derived(client):
    token = await _register(client, "tax-cls-override@example.com")
    asset_id = await _create_asset(client, token, name="Bitcoin", asset_type="crypto", isin=None)

    set_response = await client.put(
        f"/api/v1/tax/asset-classifications/{asset_id}",
        json={"asset_class": "azioni"},
        params={"on": "2020-01-01"},
        headers=_auth_headers(token),
    )
    assert set_response.status_code == 200
    assert set_response.json()["asset_class"] == "azioni"
    assert set_response.json()["is_override"] is True

    list_response = await client.get(
        "/api/v1/tax/asset-classifications", params={"on": "2020-01-01"}, headers=_auth_headers(token)
    )
    view = next(v for v in list_response.json() if v["asset_id"] == asset_id)
    assert view["asset_class"] == "azioni"
    assert view["is_override"] is True

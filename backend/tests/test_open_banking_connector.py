"""Connettore Enable Banking: normalizzazione e client HTTP, interamente con
risposte mockate (`httpx_mock`) e dati sintetici — mai conti ne' credenziali
reali. I formati di richiesta/risposta seguono la documentazione ufficiale
dell'API (https://enablebanking.com/docs/api/reference/).
"""
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import jwt
import pytest
from cryptography import x509

from app.openbanking import enable_banking
from app.openbanking.base import FetchStats, PsuContext
from app.openbanking.enable_banking import (
    EnableBankingConnector,
    normalize_transaction,
    normalize_transaction_ex,
)
from app.openbanking.errors import (
    AuthorizationExpiredError,
    OpenBankingAuthError,
    OpenBankingError,
    ProviderUnavailableError,
    RateLimitedError,
)
from app.openbanking.keys import generate_keypair

BASE = "https://api.enablebanking.com"
APP_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(scope="module")
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def connector(keypair) -> EnableBankingConnector:
    return EnableBankingConnector(application_id=APP_ID, private_key_pem=keypair[0])


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(enable_banking, "_BACKOFF_SECONDS", (0.0, 0.0))


def _tx(**overrides) -> dict:
    base = {
        "entry_reference": "ref-1",
        "transaction_amount": {"currency": "EUR", "amount": "12.30"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "booking_date": "2026-03-02",
        "value_date": "2026-03-03",
        "creditor": {"name": "Supermercato Rossi"},
        "creditor_account": {"iban": "IT60X0542811101000000123456"},
        "debtor": {"name": "Mario Titolare"},
        "remittance_information": ["Spesa  settimanale", "carta 1234"],
        "balance_after_transaction": {"currency": "EUR", "amount": "987.65"},
        "bank_transaction_code": {"description": "Pagamento POS"},
        "reference_number": "RF123",
    }
    base.update(overrides)
    return base


# ---- normalizzazione --------------------------------------------------------


def test_debit_is_negative_and_uses_creditor_as_counterparty():
    tx = normalize_transaction(_tx())
    assert tx is not None
    assert tx.amount == Decimal("-12.30")
    assert tx.currency == "EUR"
    assert tx.counterparty_name == "Supermercato Rossi"
    assert tx.counterparty_iban == "IT60X0542811101000000123456"
    assert tx.booking_date == date(2026, 3, 2)
    assert tx.value_date == date(2026, 3, 3)
    assert tx.balance_after == Decimal("987.65")
    assert tx.external_id == "ref-1"
    assert tx.status == "booked"
    assert tx.bank_transaction_code == "Pagamento POS"


def test_credit_is_positive_and_uses_debtor_as_counterparty():
    tx = normalize_transaction(
        _tx(credit_debit_indicator="CRDT", debtor={"name": "Azienda Bianchi"}, debtor_account={"iban": "IT00"})
    )
    assert tx.amount == Decimal("12.30")
    assert tx.counterparty_name == "Azienda Bianchi"
    assert tx.counterparty_iban == "IT00"


def test_amount_sign_comes_from_indicator_even_if_provider_sends_negative():
    tx = normalize_transaction(_tx(transaction_amount={"currency": "EUR", "amount": "-5.00"}))
    assert tx.amount == Decimal("-5.00")
    tx = normalize_transaction(
        _tx(credit_debit_indicator="CRDT", transaction_amount={"currency": "EUR", "amount": "-5.00"})
    )
    assert tx.amount == Decimal("5.00")


def test_description_joins_remittance_lines_and_collapses_spaces():
    tx = normalize_transaction(_tx())
    assert tx.description == "Spesa  settimanale carta 1234"


def test_description_falls_back_to_counterparty_then_generic():
    assert normalize_transaction(_tx(remittance_information=[])).description == "Supermercato Rossi"
    bare = _tx(remittance_information=None, creditor=None, bank_transaction_code=None)
    assert normalize_transaction(bare).description == "Movimento"


@pytest.mark.parametrize("status", ["CNCL", "RJCT", "SCHD"])
def test_cancelled_rejected_and_scheduled_are_skipped(status):
    assert normalize_transaction(_tx(status=status)) is None


def test_pending_is_flagged_pending():
    assert normalize_transaction(_tx(status="PDNG")).status == "pending"


def test_row_without_any_date_or_amount_is_skipped():
    no_dates = _tx(booking_date=None, value_date=None, transaction_date=None)
    assert normalize_transaction(no_dates) is None
    assert normalize_transaction(_tx(transaction_amount={})) is None


def test_transaction_id_is_never_used_as_external_id():
    # Per la documentazione `transaction_id` puo' cambiare tra una lettura e l'altra.
    assert normalize_transaction(_tx(entry_reference=None, transaction_id="tid-9")).external_id is None
    assert normalize_transaction(_tx(entry_reference=None)).external_id is None


# ---- autenticazione --------------------------------------------------------


async def test_requests_carry_a_valid_rs256_jwt_with_application_id_as_kid(connector, keypair, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", json={"aspsps": []})
    await connector.list_institutions("it")

    token = httpx_mock.get_requests()[0].headers["Authorization"].removeprefix("Bearer ")
    public_key = x509.load_pem_x509_certificate(keypair[1].encode()).public_key()
    claims = jwt.decode(token, public_key, algorithms=["RS256"], audience="api.enablebanking.com")
    assert claims["iss"] == "enablebanking.com"
    assert claims["exp"] - claims["iat"] <= 86400
    assert jwt.get_unverified_header(token)["kid"] == APP_ID


# ---- istituti ---------------------------------------------------------------


async def test_list_institutions_parses_and_sorts_and_skips_incomplete(connector, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT",
        json={
            "aspsps": [
                {"name": "Zeta Banca", "country": "IT", "logo": "https://x/z.png", "psu_types": ["personal"],
                 "maximum_consent_validity": 15552000, "beta": True},
                {"name": "Alfa Banca", "country": "IT", "psu_types": ["personal", "business"]},
                {"country": "IT"},
            ]
        },
    )
    result = await connector.list_institutions("IT")
    assert [i.name for i in result] == ["Alfa Banca", "Zeta Banca"]
    assert result[1].maximum_consent_validity_seconds == 15552000
    assert result[1].beta is True


# ---- autorizzazione --------------------------------------------------------


async def test_start_authorization_sends_expected_body(connector, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/auth", method="POST", json={"url": "https://auth.example/start", "authorization_id": "auth-1"}
    )
    valid_until = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    result = await connector.start_authorization(
        "Poste Italiane", "IT", redirect_url="https://lumio.example/cb", state="st", valid_until=valid_until
    )
    assert result.url == "https://auth.example/start"
    assert result.authorization_id == "auth-1"
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["aspsp"] == {"name": "Poste Italiane", "country": "IT"}
    assert body["state"] == "st"
    assert body["redirect_url"] == "https://lumio.example/cb"
    assert body["psu_type"] == "personal"
    assert body["access"]["transactions"] is True and body["access"]["balances"] is True
    assert body["access"]["valid_until"].startswith("2026-09-01T12:00:00")


async def test_start_authorization_without_url_is_an_error(connector, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/auth", method="POST", json={})
    with pytest.raises(OpenBankingError):
        await connector.start_authorization(
            "X", "IT", redirect_url="https://l/cb", state="s", valid_until=datetime.now(UTC)
        )


async def test_complete_authorization_returns_session_and_skips_accounts_without_uid(connector, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/sessions",
        method="POST",
        json={
            "session_id": "sess-1",
            "access": {"valid_until": "2026-09-01T12:00:00Z"},
            "accounts": [
                {"uid": "acc-1", "account_id": {"iban": "IT60X0542811101000000123456"}, "name": "Conto",
                 "product": "Conto Base", "currency": "EUR", "cash_account_type": "CACC"},
                {"account_id": {"iban": "IT00NOUID"}, "currency": "EUR"},
            ],
        },
    )
    session = await connector.complete_authorization("the-code")
    assert json.loads(httpx_mock.get_requests()[0].content) == {"code": "the-code"}
    assert session.session_id == "sess-1"
    assert session.valid_until == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    assert [a.uid for a in session.accounts] == ["acc-1"]
    assert session.accounts[0].iban == "IT60X0542811101000000123456"


# ---- saldi e movimenti -------------------------------------------------------


async def test_get_balances(connector, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/accounts/acc-1/balances",
        json={"balances": [
            {"name": "Booked", "balance_amount": {"currency": "EUR", "amount": "10.50"}, "balance_type": "CLBD"},
            {"name": "bad", "balance_amount": {}, "balance_type": "CLAV"},
        ]},
    )
    balances = await connector.get_balances("acc-1")
    assert len(balances) == 1
    assert balances[0].amount == Decimal("10.50") and balances[0].balance_type == "CLBD"


async def test_get_transactions_follows_continuation_key_and_asks_only_booked(connector, httpx_mock):
    pattern = re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*")
    httpx_mock.add_response(
        url=pattern,
        json={"transactions": [_tx(entry_reference="a"), _tx(entry_reference="x", status="CNCL")],
              "continuation_key": "page2"},
    )
    httpx_mock.add_response(url=pattern, json={"transactions": [_tx(entry_reference="b")]})

    result = await connector.get_transactions("acc-1", date_from=date(2026, 1, 1))
    assert [t.external_id for t in result] == ["a", "b"]

    first, second = httpx_mock.get_requests()
    assert first.url.params["transaction_status"] == "BOOK"
    assert first.url.params["date_from"] == "2026-01-01"
    assert "continuation_key" not in first.url.params
    assert second.url.params["continuation_key"] == "page2"


async def test_get_transactions_longest_uses_strategy_and_ignores_date_to(connector, httpx_mock):
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*"), json={"transactions": []}
    )
    await connector.get_transactions("acc-1", date_to=date(2026, 2, 1), longest=True)
    params = httpx_mock.get_requests()[0].url.params
    assert params["strategy"] == "longest"
    assert "date_to" not in params


async def test_psu_headers_sent_only_when_user_is_present(connector, httpx_mock):
    url = re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*")
    httpx_mock.add_response(url=url, json={"transactions": []})
    httpx_mock.add_response(url=url, json={"transactions": []})
    await connector.get_transactions("acc-1")
    await connector.get_transactions("acc-1", psu=PsuContext(ip_address="203.0.113.7", user_agent="UA/1"))
    scheduled, manual = httpx_mock.get_requests()
    assert "Psu-Ip-Address" not in scheduled.headers
    assert manual.headers["Psu-Ip-Address"] == "203.0.113.7"
    assert manual.headers["Psu-User-Agent"] == "UA/1"


# ---- errori e retry ----------------------------------------------------------


async def test_session_errors_map_to_authorization_expired(connector, httpx_mock):
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*"),
        status_code=401,
        json={"error": "EXPIRED_SESSION", "message": "x"},
    )
    with pytest.raises(AuthorizationExpiredError):
        await connector.get_transactions("acc-1")


async def test_unauthorized_without_session_code_is_an_auth_error(connector, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", status_code=401, json={"message": "bad jwt"})
    with pytest.raises(OpenBankingAuthError):
        await connector.list_institutions("IT")


async def test_rate_limit_is_not_retried(connector, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", status_code=429, json={})
    with pytest.raises(RateLimitedError):
        await connector.list_institutions("IT")
    assert len(httpx_mock.get_requests()) == 1


async def test_aspsp_rate_limit_code_is_rate_limited(connector, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT", status_code=400, json={"error": "ASPSP_RATE_LIMIT_EXCEEDED"}
    )
    with pytest.raises(RateLimitedError):
        await connector.list_institutions("IT")


async def test_transient_5xx_is_retried_then_succeeds(connector, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", status_code=503, json={})
    httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", json={"aspsps": []})
    assert await connector.list_institutions("IT") == []
    assert len(httpx_mock.get_requests()) == 2


async def test_persistent_5xx_raises_provider_unavailable_after_three_attempts(connector, httpx_mock):
    for _ in range(3):
        httpx_mock.add_response(url=f"{BASE}/aspsps?country=IT", status_code=502, json={})
    with pytest.raises(ProviderUnavailableError):
        await connector.list_institutions("IT")
    assert len(httpx_mock.get_requests()) == 3


async def test_error_messages_never_include_response_body(connector, httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/aspsps?country=IT", status_code=400, json={"error": "X", "message": "IBAN IT60SECRET"}
    )
    with pytest.raises(OpenBankingError) as excinfo:
        await connector.list_institutions("IT")
    assert "SECRET" not in str(excinfo.value)


# ---- revoca -------------------------------------------------------------------


async def test_revoke_deletes_session(connector, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/sessions/sess-1", method="DELETE", status_code=204)
    await connector.revoke("sess-1")


@pytest.mark.parametrize(
    "status_code,payload", [(404, {}), (401, {"error": "CLOSED_SESSION"}), (401, {"error": "EXPIRED_SESSION"})]
)
async def test_revoke_is_idempotent_for_already_closed_sessions(connector, httpx_mock, status_code, payload):
    httpx_mock.add_response(url=f"{BASE}/sessions/sess-1", method="DELETE", status_code=status_code, json=payload)
    await connector.revoke("sess-1")


async def test_revoke_propagates_other_errors(connector, httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/sessions/sess-1", method="DELETE", status_code=400, json={})
    with pytest.raises(OpenBankingError):
        await connector.revoke("sess-1")


# ---- normalizzazione tollerante (hardening) -------------------------------------------


@pytest.mark.parametrize("placeholder", ["0", "000", "", "null", "N/A"])
def test_placeholder_entry_reference_is_not_an_external_id(placeholder):
    tx = normalize_transaction(_tx(entry_reference=placeholder))
    assert tx.external_id is None
    assert "external_id_placeholder" in tx.flags or "external_id_missing" in tx.flags


@pytest.mark.parametrize(
    "amount,expected",
    [("1.234,56", "1234.56"), ("12,5", "12.5"), ("1,234", "1234"), (" 7.00 ", "7.00"), ("1,234.50", "1234.50")],
)
def test_amount_accepts_comma_and_thousands_separators(amount, expected):
    tx = normalize_transaction(_tx(transaction_amount={"currency": "EUR", "amount": amount}, credit_debit_indicator="CRDT"))
    assert tx.amount == Decimal(expected)


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"transaction_amount": {"currency": "EUR", "amount": "0.00"}}, "zero_amount"),
        ({"transaction_amount": {"currency": "EUR", "amount": "abc"}}, "invalid_amount"),
        ({"transaction_amount": "12.00"}, "invalid_amount"),
        ({"transaction_amount": {"currency": "EURO", "amount": "1.00"}}, "invalid_currency"),
        ({"transaction_amount": {"currency": "e1", "amount": "1.00"}}, "invalid_currency"),
        ({"booking_date": None, "value_date": None, "transaction_date": None}, "no_date"),
        ({"status": "CNCL"}, "status_skipped"),
    ],
)
def test_unusable_rows_are_discarded_with_a_reason(overrides, reason):
    tx, why = normalize_transaction_ex(_tx(**overrides))
    assert tx is None and why == reason


def test_malformed_payloads_never_raise():
    for raw in (None, "x", [], 5, {"transaction_amount": []}):
        tx, why = normalize_transaction_ex(raw)
        assert tx is None and why is not None
    tx = normalize_transaction(
        _tx(creditor="Mario", creditor_account=["x"], bank_transaction_code="POS",
            balance_after_transaction="12", remittance_information={"a": 1})
    )
    assert tx is not None and tx.counterparty_name is None and tx.balance_after is None


def test_missing_indicator_falls_back_to_the_amount_sign():
    credit = normalize_transaction(_tx(credit_debit_indicator=None))
    assert credit.amount == Decimal("12.30") and "indicator_missing" in credit.flags
    debit = normalize_transaction(_tx(credit_debit_indicator="??", transaction_amount={"currency": "EUR", "amount": "-4.00"}))
    assert debit.amount == Decimal("-4.00")


def test_bank_code_and_sub_code_are_kept():
    tx = normalize_transaction(_tx(bank_transaction_code={"description": "Pagamento POS", "code": "PMNT", "sub_code": "CCRD"}))
    assert tx.bank_code == "PMNT" and tx.bank_sub_code == "CCRD"


async def test_stats_count_discards_statuses_and_sub_codes_without_values(connector, httpx_mock):
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*"),
        json={
            "transactions": [
                _tx(entry_reference="a", bank_transaction_code={"description": "x", "sub_code": "UPCT"}),
                _tx(entry_reference="b", transaction_amount={"currency": "EUR", "amount": "0"}),
                _tx(entry_reference="c", status="PDNG"),
                "garbage",
            ]
        },
    )
    stats = FetchStats()
    result = await connector.get_transactions("acc-1", stats=stats)
    assert [t.external_id for t in result] == ["a"]
    data = stats.as_dict()
    assert data["raw_count"] == 4 and data["accepted"] == 1
    assert data["discarded"] == {"zero_amount": 1, "not_booked": 1, "malformed": 1}
    assert data["sub_codes"] == {"UPCT": 1} and data["status_counts"]["PDNG"] == 1
    assert "Supermercato" not in str(data) and "12.30" not in str(data)


async def test_repeated_continuation_key_is_an_incomplete_fetch(connector, httpx_mock):
    pattern = re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*")
    httpx_mock.add_response(url=pattern, json={"transactions": [_tx(entry_reference="a")], "continuation_key": "k"})
    httpx_mock.add_response(url=pattern, json={"transactions": [_tx(entry_reference="b")], "continuation_key": "k"})
    with pytest.raises(OpenBankingError) as info:
        await connector.get_transactions("acc-1")
    assert info.value.code == "incomplete_fetch"


async def test_page_limit_is_an_incomplete_fetch_not_a_silent_truncation(connector, httpx_mock, monkeypatch):
    monkeypatch.setattr(enable_banking, "_MAX_PAGES", 2)
    counter = iter(range(100))

    def reply(request):
        return httpx.Response(200, json={"transactions": [], "continuation_key": f"k{next(counter)}"})

    httpx_mock.add_callback(reply, url=re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*"))
    with pytest.raises(OpenBankingError) as info:
        await connector.get_transactions("acc-1")
    assert info.value.code == "incomplete_fetch"


# ---- dump diagnostico (opt-in) --------------------------------------------------------


async def test_debug_dump_is_off_by_default(connector, httpx_mock, tmp_path, monkeypatch):
    from app.core.config import get_settings

    assert get_settings().open_banking_debug_dump_dir == ""
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*"), json={"transactions": [_tx()]}
    )
    await connector.get_transactions("acc-1")
    assert list(tmp_path.iterdir()) == []


async def test_debug_dump_writes_raw_first_transactions_to_a_private_file(connector, httpx_mock, tmp_path, monkeypatch):
    import os
    import stat

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "open_banking_debug_dump_dir", str(tmp_path / "dump"))
    monkeypatch.setattr(get_settings(), "open_banking_debug_dump_limit", 2)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*"),
        json={"transactions": [_tx(entry_reference=f"r{i}", extra_field="visibile") for i in range(5)]},
    )

    result = await connector.get_transactions("acc-1")

    assert len(result) == 5  # la sync non cambia
    files = list((tmp_path / "dump").iterdir())
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["transactions_in_page"] == 5 and payload["dumped"] == 2
    assert payload["transactions"][0]["extra_field"] == "visibile"  # campi sconosciuti inclusi
    assert "transactions" in payload["top_level_keys"]
    if os.name != "nt":
        assert stat.S_IMODE(files[0].stat().st_mode) == 0o600


async def test_debug_dump_failure_never_breaks_the_read(connector, httpx_mock, tmp_path, monkeypatch):
    from app.core.config import get_settings

    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(get_settings(), "open_banking_debug_dump_dir", str(blocker / "sub"))  # non creabile
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(BASE)}/accounts/acc-1/transactions.*"), json={"transactions": [_tx()]}
    )
    assert len(await connector.get_transactions("acc-1")) == 1

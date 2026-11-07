"""Open Banking: cursore recuperabile, tombstone, id riusati, doppio canale,
REVIEW non riaccodate, statistiche di sync. Provider finto e dati sintetici.
Richiede `OPEN_BANKING_ENABLED=true` (vedi test_open_banking_api.py)."""
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.redis import redis_client
from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.open_banking import BankConnectionAccount, BankTransactionTombstone
from app.models.transaction import Transaction
from app.models.transaction_review_item import TransactionReviewItem
from app.openbanking.base import Balance
from app.openbanking.errors import OpenBankingError, ProviderUnavailableError, RateLimitedError
from app.services import bank_sync_service, transaction_type_mapping_service
from app.services.transfer_recognition import reapply_internal_transfer_detection
from app.services.bank_sync_service import count_balance_gaps
from tests.test_open_banking_api import (  # noqa: F401  (fixture autouse e helper condivisi)
    _clean_sync_keys,
    _FakeConnector,
    _h,
    _linked_and_enabled,
    _ntx,
    _link_bank,
    _redirect_uri,
    _register,
    _setup_credentials,
    _enable_first_account,
    _connections,
    _use,
)


async def _account(user_id, account_id) -> BankConnectionAccount:
    async with rls_session(user_id) as db:
        return await db.get(BankConnectionAccount, account_id)


async def _transactions(user_id) -> list[Transaction]:
    async with rls_session(user_id) as db:
        return list((await db.scalars(select(Transaction).order_by(Transaction.transaction_date))).all())


# ---- cursore ---------------------------------------------------------------------


async def test_cursor_does_not_advance_when_persistence_is_skipped(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-1@example.com")
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-5.00", date(2026, 3, 1), "A")]]))
    monkeypatch.setattr("app.worker.jobs.import_job._insert_transactions_and_complete", AsyncMock(return_value=False))

    summary = await bank_sync_service.sync_connection(connection_id, user_id)

    assert summary.error_code == "persist_failed" and summary.imported == 0
    stored = await _account(user_id, account_id)
    assert stored.last_booked_date is None and stored.transactions_imported == 0
    assert stored.last_sync_stats["error"] == "persist_failed"


async def test_cursor_is_never_in_the_future(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-2@example.com")
    future = datetime.now(UTC).date() + timedelta(days=20)
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-5.00", date(2026, 3, 1), "A"), _ntx("e2", "-6.00", future, "B")]]))

    summary = await bank_sync_service.sync_connection(connection_id, user_id)

    assert summary.error_code is None
    assert (await _account(user_id, account_id)).last_booked_date == datetime.now(UTC).date()


async def test_deleting_an_open_banking_import_resets_cursor_and_resync_restores_movements(
    client, httpx_mock, monkeypatch
):
    token, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-3@example.com")
    batch = [_ntx("e1", "-5.00", date(2026, 3, 1), "A"), _ntx("e2", "-6.00", date(2026, 3, 2), "B")]
    fake = _FakeConnector([batch, batch])
    _use(monkeypatch, fake)
    assert (await bank_sync_service.sync_connection(connection_id, user_id)).imported == 2

    async with rls_session(user_id) as db:
        import_id = (await db.scalars(select(Import.id))).one()
    deleted = await client.delete(f"/api/v1/imports/{import_id}", headers=_h(token))
    assert deleted.status_code == 200
    stored = await _account(user_id, account_id)
    assert stored.last_booked_date is None and stored.transactions_imported == 0
    assert await _transactions(user_id) == []

    again = await bank_sync_service.sync_connection(connection_id, user_id)

    assert again.imported == 2
    assert fake.calls[1]["longest"] is True and fake.calls[1]["date_from"] is None
    assert len(await _transactions(user_id)) == 2  # tornati, senza duplicati
    assert (await _account(user_id, account_id)).transactions_imported == 2


async def test_changing_the_mapped_account_resets_cursor_and_counter(client, httpx_mock, monkeypatch):
    token, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-4@example.com")
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-5.00", date(2026, 3, 1), "A")]]))
    await bank_sync_service.sync_connection(connection_id, user_id)
    other = await client.post(
        "/api/v1/accounts", json={"name": "Altro", "account_type": "checking", "currency": "EUR"}, headers=_h(token)
    )
    assert other.status_code == 201, other.text

    patched = await client.patch(
        f"/api/v1/open-banking/connections/{connection_id}/accounts/{account_id}",
        json={"financial_account_id": other.json()["id"]},
        headers=_h(token),
    )

    assert patched.status_code == 200
    stored = await _account(user_id, account_id)
    assert stored.last_booked_date is None and stored.transactions_imported == 0 and stored.last_sync_stats is None


async def test_deleting_the_mapped_lumio_account_leaves_no_orphan_cursor(client, httpx_mock, monkeypatch):
    token, user_id, _w, connection_id, account_id, fin_id = await _linked_and_enabled(
        client, httpx_mock, "hd-5@example.com"
    )
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-5.00", date(2026, 3, 1), "A")]]))
    await bank_sync_service.sync_connection(connection_id, user_id)

    assert (await client.delete(f"/api/v1/accounts/{fin_id}", headers=_h(token))).status_code == 204

    stored = await _account(user_id, account_id)
    assert stored.financial_account_id is None and stored.last_booked_date is None and stored.transactions_imported == 0


# ---- rileggi storico e tombstone ------------------------------------------------------


async def test_manual_delete_leaves_a_tombstone_and_resync_history_brings_it_back(client, httpx_mock, monkeypatch):
    token, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-6@example.com")
    batch = [_ntx("e1", "-5.00", date(2026, 3, 1), "A"), _ntx("e2", "-6.00", date(2026, 3, 2), "B")]
    fake = _FakeConnector([batch, batch, batch])
    _use(monkeypatch, fake)
    await bank_sync_service.sync_connection(connection_id, user_id)
    victim = next(t for t in await _transactions(user_id) if t.external_id == "e1")
    assert (await client.delete(f"/api/v1/transactions/{victim.id}", headers=_h(token))).status_code == 204
    async with rls_session(user_id) as db:
        assert (await db.scalars(select(BankTransactionTombstone.external_id))).all() == ["e1"]

    second = await bank_sync_service.sync_connection(connection_id, user_id)
    assert second.imported == 0
    assert [t.external_id for t in await _transactions(user_id)] == ["e2"]
    assert (await _account(user_id, account_id)).last_sync_stats["persist"]["tombstoned"] == 1

    enqueue = AsyncMock()
    monkeypatch.setattr("app.api.v1.open_banking.enqueue_bank_sync", enqueue)
    resync = await client.post(
        f"/api/v1/open-banking/connections/{connection_id}/accounts/{account_id}/resync-history", headers=_h(token)
    )
    assert resync.status_code == 202
    enqueue.assert_awaited_once()
    stored = await _account(user_id, account_id)
    assert stored.last_booked_date is None
    async with rls_session(user_id) as db:
        assert (await db.scalars(select(BankTransactionTombstone))).all() == []

    third = await bank_sync_service.sync_connection(connection_id, user_id)
    assert third.imported == 1 and sorted(t.external_id for t in await _transactions(user_id)) == ["e1", "e2"]


async def test_resync_history_respects_lock_and_rate_limit_backoff(client, httpx_mock, monkeypatch):
    token, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-7@example.com")
    monkeypatch.setattr("app.api.v1.open_banking.enqueue_bank_sync", AsyncMock())
    url = f"/api/v1/open-banking/connections/{connection_id}/accounts/{account_id}/resync-history"

    assert await bank_sync_service.try_acquire_lock(connection_id)
    assert (await client.post(url, headers=_h(token))).status_code == 409
    await bank_sync_service.release_lock(connection_id)

    _use(monkeypatch, _FakeConnector([]))
    fake = _FakeConnector([])
    fake.error = RateLimitedError("429", http_status=429)
    _use(monkeypatch, fake)
    summary = await bank_sync_service.sync_connection(connection_id, user_id)
    assert summary.error_code == "rate_limited"
    assert (await client.post(url, headers=_h(token))).status_code == 429


async def test_resync_history_requires_ownership(client, httpx_mock, monkeypatch):
    token, _u, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-8@example.com")
    other_token, _ou, _ow = await _register(client, "hd-8-other@example.com")
    url = f"/api/v1/open-banking/connections/{connection_id}/accounts/{account_id}/resync-history"
    assert (await client.post(url, headers=_h(other_token))).status_code == 404
    assert (await client.post(url, headers={})).status_code in (401, 403)
    assert token  # il proprietario non e' stato toccato


# ---- dedup: id riusati, doppio canale, REVIEW ----------------------------------------


async def test_same_id_with_different_content_is_a_distinct_movement(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-9@example.com")
    fake = _FakeConnector([
        [_ntx("e1", "-5.00", date(2026, 3, 1), "A")],
        [_ntx("e1", "-5.00", date(2026, 3, 2), "A"), _ntx("e1", "-9.00", date(2026, 3, 4), "Altro importo")],
    ])
    _use(monkeypatch, fake)
    await bank_sync_service.sync_connection(connection_id, user_id)

    second = await bank_sync_service.sync_connection(connection_id, user_id)

    # stesso importo, data spostata di 1 giorno = stesso movimento; importo diverso = movimento nuovo
    assert second.imported == 1
    assert sorted(t.amount for t in await _transactions(user_id)) == [Decimal("-9.00"), Decimal("-5.00")]
    assert (await _account(user_id, account_id)).last_sync_stats["persist"]["id_reused_distinct"] == 1


async def test_duplicates_inside_one_response_collapse_only_when_content_matches(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "hd-10@example.com")
    same = _ntx("e1", "-5.00", date(2026, 3, 1), "A")
    _use(monkeypatch, _FakeConnector([[same, same, _ntx("e1", "-7.00", date(2026, 3, 1), "B")]]))

    summary = await bank_sync_service.sync_connection(connection_id, user_id)

    assert summary.imported == 2 and summary.duplicates >= 1


async def test_review_row_is_not_requeued_on_every_sync(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-11@example.com")
    # Movimento "da PDF" (senza id banca) e lo stesso movimento da Open Banking con
    # data, tipo e descrizione diversi: mai un duplicato automatico, sempre REVIEW.
    pdf_like = _ntx(None, "-20.00", date(2026, 3, 5), "Pagamento carta")
    bank_row = _ntx("r1", "-20.00", date(2026, 3, 6), "POS NEGOZIO ROSSI")
    _use(monkeypatch, _FakeConnector([[pdf_like], [bank_row], [bank_row]]))
    await bank_sync_service.sync_connection(connection_id, user_id)

    second = await bank_sync_service.sync_connection(connection_id, user_id)
    assert second.imported == 0 and second.review_pending == 1
    third = await bank_sync_service.sync_connection(connection_id, user_id)

    assert third.review_pending == 0 and third.imported == 0
    async with rls_session(user_id) as db:
        items = (await db.scalars(select(TransactionReviewItem))).all()
        assert [(i.external_id, i.status) for i in items] == [("r1", "pending")]
    assert (await _account(user_id, account_id)).last_sync_stats["persist"]["review_known"] == 1


async def test_foreign_currency_rows_are_not_imported_and_are_counted(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-12@example.com")
    usd = _ntx("u1", "-5.00", date(2026, 3, 1), "Acquisto estero")
    usd.currency = "USD"
    _use(monkeypatch, _FakeConnector([[usd, _ntx("e1", "-3.00", date(2026, 3, 2), "A")]]))

    summary = await bank_sync_service.sync_connection(connection_id, user_id)

    assert summary.imported == 1
    assert (await _account(user_id, account_id)).last_sync_stats["persist"]["foreign_currency"] == 1


# ---- diagnostica, saldo, resilienza ---------------------------------------------------


async def test_sync_stats_contain_counts_only(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-13@example.com")
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-12.50", date(2026, 3, 1), "Caffe Segreto", counterparty_name="Bar Roma")]]))

    await bank_sync_service.sync_connection(connection_id, user_id)

    stats = (await _account(user_id, account_id)).last_sync_stats
    dumped = json.dumps(stats)
    assert stats["persist"]["imported"] == 1 and "fetch" in stats
    for secret in ("Caffe", "Bar Roma", "12.50", "e1"):
        assert secret not in dumped


async def test_balance_snapshot_prefers_closing_booked_and_flags_nothing_when_continuous(
    client, httpx_mock, monkeypatch
):
    class _WithBalances(_FakeConnector):
        async def get_balances(self, uid, *, psu=None):
            return [Balance("ITAV", Decimal("99.00"), "EUR"), Balance("CLBD", Decimal("120.00"), "EUR")]

    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-14@example.com")
    _use(monkeypatch, _WithBalances([[_ntx("e1", "-5.00", date(2026, 3, 1), "A")]]))

    await bank_sync_service.sync_connection(connection_id, user_id)

    snapshot = (await _account(user_id, account_id)).balance_snapshot
    assert snapshot["type"] == "CLBD" and snapshot["amount"] == "120.00" and snapshot["continuity_gaps"] == 0


def _with_balance(amount: str, balance: str):
    tx = _ntx(None, amount, date(2026, 3, 1), "x")
    tx.balance_after = Decimal(balance)
    return tx


def test_balance_continuity_detects_a_missing_movement_regardless_of_order():
    chain = [_with_balance("-10.00", "90.00"), _with_balance("-5.00", "85.00"), _with_balance("-5.00", "80.00")]
    assert count_balance_gaps(list(reversed(chain))) == (3, 0)
    broken = [_with_balance("-10.00", "90.00"), _with_balance("-5.00", "70.00"), _with_balance("-5.00", "65.00")]
    assert count_balance_gaps(broken) == (3, 1)
    assert count_balance_gaps(chain[:2]) == (2, 0)  # poche righe: controllo non significativo


async def test_wrong_period_error_falls_back_to_the_longest_read(client, httpx_mock, monkeypatch):
    class _Picky(_FakeConnector):
        async def get_transactions(self, uid, *, date_from=None, date_to=None, longest=False, psu=None, stats=None):
            self.calls.append({"longest": longest, "date_from": date_from})
            if not longest:
                raise OpenBankingError("periodo", code="WRONG_TRANSACTIONS_PERIOD", http_status=422)
            return self.batches.pop(0)

    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-15@example.com")
    first = [_ntx("e1", "-5.00", date(2026, 3, 1), "A")]
    fake = _Picky([first, first + [_ntx("e2", "-6.00", date(2026, 3, 2), "B")]])
    _use(monkeypatch, fake)
    await bank_sync_service.sync_connection(connection_id, user_id)  # primo giro: longest

    second = await bank_sync_service.sync_connection(connection_id, user_id)

    assert second.error_code is None and second.imported == 1
    assert [c["longest"] for c in fake.calls] == [True, False, True]


async def test_provider_failure_leaves_cursor_and_records_the_error(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, account_id, _f = await _linked_and_enabled(client, httpx_mock, "hd-16@example.com")
    fake = _FakeConnector([])
    fake.error = ProviderUnavailableError("giu'")
    _use(monkeypatch, fake)

    summary = await bank_sync_service.sync_connection(connection_id, user_id)

    assert summary.error_code == "provider_unavailable"
    stored = await _account(user_id, account_id)
    assert stored.last_booked_date is None and stored.last_sync_stats == {"error": "provider_unavailable"}


async def test_skipped_scheduled_sync_does_not_consume_the_attempt_window(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "hd-17@example.com")
    _use(monkeypatch, _FakeConnector([]))
    assert await bank_sync_service.try_acquire_lock(connection_id)

    summary = await bank_sync_service.sync_connection(connection_id, user_id, scheduled=True)

    assert summary.skipped is True
    assert not await redis_client.exists(f"bank_sync:attempt:{connection_id}")
    await bank_sync_service.release_lock(connection_id)


async def test_error_backoff_is_longer_for_errors_that_need_the_user(client, httpx_mock, monkeypatch):
    _t, user_id, _w, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "hd-18@example.com")
    fake = _FakeConnector([])
    fake.error = ProviderUnavailableError("giu'")
    _use(monkeypatch, fake)
    await bank_sync_service.sync_connection(connection_id, user_id, scheduled=True)
    transient_ttl = await redis_client.ttl(f"bank_sync:attempt:{connection_id}")

    await redis_client.delete(f"bank_sync:attempt:{connection_id}")
    fake.error = RateLimitedError("429", http_status=429)
    await bank_sync_service.sync_connection(connection_id, user_id, scheduled=True)
    rate_ttl = await redis_client.ttl(f"bank_sync:attempt:{connection_id}")

    assert 0 < transient_ttl <= 3600 and rate_ttl > 3600



# ---- tipi, trasferimenti, rinnovo ---------------------------------------------------------


async def test_open_banking_labels_can_be_mapped_and_reapplied_retroactively(client, httpx_mock, monkeypatch):
    _t, user_id, workspace_id, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "hd-19@example.com")
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-5.00", date(2026, 3, 1), "A"), _ntx("e2", "7.00", date(2026, 3, 2), "B")]]))
    await bank_sync_service.sync_connection(connection_id, user_id)

    async with rls_session(user_id) as db:
        assert "open_banking" in await transaction_type_mapping_service.list_used_parser_types(db, workspace_id)
        labels = await transaction_type_mapping_service.list_observed_labels(db, workspace_id, "open_banking")
        assert [(label.source_type_raw, label.total_count) for label in labels] == [("Pagamento POS", 2)]
        result = await transaction_type_mapping_service.reapply_mapping(
            db, workspace_id, "open_banking", "Pagamento POS", "fee"
        )
        assert result.updated == 2 and result.skipped == 0
        await db.commit()
    assert {t.transaction_type for t in await _transactions(user_id)} == {"fee"}


async def test_saved_open_banking_mapping_applies_to_the_next_sync(client, httpx_mock, monkeypatch):
    _t, user_id, workspace_id, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "hd-20@example.com")
    async with rls_session(user_id) as db:
        await transaction_type_mapping_service.upsert_mapping(db, workspace_id, "open_banking", "Pagamento POS", "fee")
        await db.commit()
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-5.00", date(2026, 3, 1), "A")]]))

    await bank_sync_service.sync_connection(connection_id, user_id)

    assert [t.transaction_type for t in await _transactions(user_id)] == ["fee"]


async def test_reapply_transfer_detection_covers_open_banking_rows(client, httpx_mock, monkeypatch):
    token, user_id, workspace_id, connection_id, _a, _f = await _linked_and_enabled(client, httpx_mock, "hd-21@example.com")
    own_iban = "DE89370400440532013000"
    _use(monkeypatch, _FakeConnector([[_ntx("e1", "-50.00", date(2026, 3, 1), "Giroconto", counterparty_iban=own_iban)]]))
    await bank_sync_service.sync_connection(connection_id, user_id)
    assert [t.transaction_type for t in await _transactions(user_id)] == ["expense"]

    created = await client.post(
        "/api/v1/accounts",
        json={"name": "Risparmio", "account_type": "savings", "currency": "EUR", "iban": own_iban},
        headers=_h(token),
    )
    assert created.status_code == 201, created.text
    async with rls_session(user_id) as db:
        await reapply_internal_transfer_detection(db, workspace_id)
        await db.commit()

    assert [t.transaction_type for t in await _transactions(user_id)] == ["transfer"]


async def test_renewal_inherits_state_even_when_the_iban_format_differs(client, httpx_mock):
    token, user_id, _ = await _register(client, "hd-22@example.com")
    await _setup_credentials(client, token)
    await _link_bank(client, token, httpx_mock, session_id="sess-1")
    _cid, _aid, financial_account_id = await _enable_first_account(client, token)
    async with rls_session(user_id) as db:
        account = (await db.scalars(select(BankConnectionAccount))).one()
        account.iban = account.iban.lower()[:4] + " " + account.iban[4:]
        account.last_booked_date = date(2026, 3, 1)
        await db.commit()

    await _link_bank(client, token, httpx_mock, session_id="sess-2", revoke_previous="sess-1")

    account = (await _connections(client, token))[0]["accounts"][0]
    assert account["enabled"] is True and account["financial_account_id"] == financial_account_id
    async with rls_session(user_id) as db:
        assert (await db.scalars(select(BankConnectionAccount))).one().last_booked_date == date(2026, 3, 1)

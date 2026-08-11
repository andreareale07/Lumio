"""Test del servizio di mappatura tipi transazione configurabile per
parser (milestone 09.5) — setup via ORM diretto (workspace/conto/import/
transazioni), stesso principio "bypassa l'API per il setup" di
test_rls_market_data.py: andare attraverso un vero upload/parsing PDF per
testare solo questo strato sarebbe sproporzionato.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.services.transaction_type_mapping_service import (
    delete_mapping,
    list_observed_labels,
    list_used_parser_types,
    reapply_mapping,
    resolve_transaction_type,
    upsert_mapping,
)

_TR_BANK_ID = uuid.UUID("6bb6eb78-276d-4b2f-ac63-8eef2c57d307")
_TR_BANK_PARSER_ID = uuid.UUID("1f6a5b19-3b40-4b3e-9a7b-2e0d6f1c9a44")
_PARSER_TYPE = "trade_republic_pdf"


async def _create_user_with_workspace(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name) "
                "VALUES (:id, :email, 'x', 'Test')"
            ),
            {"id": str(user_id), "email": email},
        )
        await session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
        )
        workspace_id = (
            await session.execute(
                text(
                    "INSERT INTO workspaces (name, owner_user_id) "
                    "VALUES ('Personale', :owner) RETURNING id"
                ),
                {"owner": str(user_id)},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES (:w, :u, 'owner')"
            ),
            {"w": str(workspace_id), "u": str(user_id)},
        )
        await session.commit()
    return user_id, workspace_id


async def _create_account(db, workspace_id: uuid.UUID) -> uuid.UUID:
    account_id = (
        await db.execute(
            text(
                "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                "VALUES (:w, 'Trade Republic', 'brokerage', 'EUR') RETURNING id"
            ),
            {"w": str(workspace_id)},
        )
    ).scalar_one()
    return account_id


async def _create_pdf_import(db, workspace_id: uuid.UUID, account_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
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
    return import_row.id


async def _create_transaction(
    db,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    import_id: uuid.UUID,
    *,
    source_type_raw: str,
    transaction_type: str,
    direction: str,
    amount: str = "-10.00",
) -> Transaction:
    txn = Transaction(
        workspace_id=workspace_id,
        financial_account_id=account_id,
        import_id=import_id,
        transaction_date=date(2026, 1, 1),
        description_raw="riga di test",
        amount=amount,
        currency="EUR",
        direction=direction,
        transaction_type=transaction_type,
        source_type_raw=source_type_raw,
    )
    db.add(txn)
    await db.flush()
    return txn


async def _setup_workspace_with_bonifico_transactions(email: str):
    user_id, workspace_id = await _create_user_with_workspace(email)
    async with rls_session(user_id) as db:
        account_id = await _create_account(db, workspace_id)
        import_id = await _create_pdf_import(db, workspace_id, account_id, user_id)
        # Due "Bonifico" ancora al default (credit->income, debit->expense,
        # vedi trade_republic.py:_transaction_type) + una gia' corretta a
        # mano dall'utente (income -> refund, un default che il parser non
        # produrrebbe MAI per un "Bonifico").
        txn_default_credit = await _create_transaction(
            db, workspace_id, account_id, import_id,
            source_type_raw="Bonifico", transaction_type="income", direction="credit",
        )
        txn_default_debit = await _create_transaction(
            db, workspace_id, account_id, import_id,
            source_type_raw="Bonifico", transaction_type="expense", direction="debit",
        )
        txn_manually_edited = await _create_transaction(
            db, workspace_id, account_id, import_id,
            source_type_raw="Bonifico", transaction_type="refund", direction="credit",
        )
        await db.commit()
    return user_id, workspace_id, (txn_default_credit.id, txn_default_debit.id, txn_manually_edited.id)


async def test_list_used_parser_types_returns_only_parsers_actually_imported():
    user_id, workspace_id, _ = await _setup_workspace_with_bonifico_transactions("ttm-parsers@example.com")
    async with rls_session(user_id) as db:
        parser_types = await list_used_parser_types(db, workspace_id)
    assert parser_types == [_PARSER_TYPE]


async def test_list_observed_labels_groups_by_label_and_current_type():
    user_id, workspace_id, _ = await _setup_workspace_with_bonifico_transactions("ttm-labels@example.com")
    async with rls_session(user_id) as db:
        labels = await list_observed_labels(db, workspace_id, _PARSER_TYPE)

    assert len(labels) == 1
    label = labels[0]
    assert label.source_type_raw == "Bonifico"
    assert label.total_count == 3
    assert label.override is None
    counts = {tc.transaction_type: tc.count for tc in label.current_types}
    assert counts == {"income": 1, "expense": 1, "refund": 1}


async def test_resolve_transaction_type_falls_back_to_default_without_override():
    user_id, workspace_id, _ = await _setup_workspace_with_bonifico_transactions("ttm-resolve-default@example.com")
    async with rls_session(user_id) as db:
        result = await resolve_transaction_type(db, workspace_id, _PARSER_TYPE, "Bonifico", default_type="income")
    assert result == "income"


async def test_resolve_transaction_type_uses_saved_override():
    user_id, workspace_id, _ = await _setup_workspace_with_bonifico_transactions("ttm-resolve-override@example.com")
    async with rls_session(user_id) as db:
        await upsert_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico", "transfer")
        await db.commit()

    async with rls_session(user_id) as db:
        result = await resolve_transaction_type(db, workspace_id, _PARSER_TYPE, "Bonifico", default_type="income")
    assert result == "transfer"


async def test_resolve_transaction_type_without_label_returns_default():
    user_id, workspace_id = await _create_user_with_workspace("ttm-resolve-nolabel@example.com")
    async with rls_session(user_id) as db:
        result = await resolve_transaction_type(db, workspace_id, _PARSER_TYPE, None, default_type="expense")
    assert result == "expense"


async def test_upsert_mapping_is_idempotent_overwrites_same_row():
    user_id, workspace_id, _ = await _setup_workspace_with_bonifico_transactions("ttm-upsert@example.com")
    async with rls_session(user_id) as db:
        await upsert_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico", "transfer")
        await upsert_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico", "fee")
        await db.commit()

    async with rls_session(user_id) as db:
        rows = (
            await db.execute(
                text(
                    "SELECT transaction_type FROM transaction_type_mappings "
                    "WHERE workspace_id = :w AND parser_type = :p AND source_type_raw = 'Bonifico'"
                ),
                {"w": str(workspace_id), "p": _PARSER_TYPE},
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].transaction_type == "fee"


async def test_delete_mapping_removes_override_returns_true():
    user_id, workspace_id, _ = await _setup_workspace_with_bonifico_transactions("ttm-delete@example.com")
    async with rls_session(user_id) as db:
        await upsert_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico", "transfer")
        await db.commit()

    async with rls_session(user_id) as db:
        deleted = await delete_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico")
        await db.commit()
    assert deleted is True

    async with rls_session(user_id) as db:
        result = await resolve_transaction_type(db, workspace_id, _PARSER_TYPE, "Bonifico", default_type="income")
    assert result == "income"


async def test_delete_mapping_returns_false_when_nothing_to_delete():
    user_id, workspace_id = await _create_user_with_workspace("ttm-delete-none@example.com")
    async with rls_session(user_id) as db:
        deleted = await delete_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico")
    assert deleted is False


async def test_reapply_mapping_updates_default_and_skips_manually_edited():
    """Regressione della decisione presa con l'utente: la rimappatura
    retroattiva non deve mai toccare una transazione il cui tipo diverge
    dal default del parser (assunta corretta a mano)."""
    user_id, workspace_id, (credit_id, debit_id, edited_id) = await _setup_workspace_with_bonifico_transactions(
        "ttm-reapply@example.com"
    )

    async with rls_session(user_id) as db:
        result = await reapply_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico", "transfer")
        await db.commit()

    assert result.updated == 2  # le due al default (credit->income, debit->expense)
    assert result.skipped == 1  # quella corretta a mano (credit->refund, non e' un default)

    async with rls_session(user_id) as db:
        rows = (
            await db.execute(
                text("SELECT id, transaction_type FROM transactions WHERE workspace_id = :w"),
                {"w": str(workspace_id)},
            )
        ).all()
    by_id = {row.id: row.transaction_type for row in rows}
    assert by_id[credit_id] == "transfer"
    assert by_id[debit_id] == "transfer"
    assert by_id[edited_id] == "refund"  # intatta


async def test_reapply_mapping_is_idempotent_second_run_updates_nothing_new():
    user_id, workspace_id, (credit_id, debit_id, edited_id) = await _setup_workspace_with_bonifico_transactions(
        "ttm-reapply-idempotent@example.com"
    )

    async with rls_session(user_id) as db:
        await reapply_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico", "transfer")
        await db.commit()

    async with rls_session(user_id) as db:
        # Seconda esecuzione: le due gia' "transfer" non coincidono piu' col
        # default del parser (income/expense), quindi vengono ora SALTATE —
        # nessun doppio conteggio, nessuna oscillazione.
        result = await reapply_mapping(db, workspace_id, _PARSER_TYPE, "Bonifico", "transfer")
        await db.commit()

    assert result.updated == 0
    assert result.skipped == 3

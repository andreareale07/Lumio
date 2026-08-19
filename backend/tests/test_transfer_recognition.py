"""Test del riconoscimento dei trasferimenti interni (milestone 09.5b,
SPEC §37) — setup via ORM diretto, stesso pattern di
test_transaction_type_mapping_service.py.
"""
import uuid
from datetime import date

from sqlalchemy import select, text

from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.models.financial_account import FinancialAccount
from app.models.financial_account_iban_history import FinancialAccountIbanHistory
from app.models.import_ import Import
from app.models.transaction import Transaction
from app.parsers.base import TransferCounterparty
from app.services.transfer_recognition import (
    archive_previous_iban,
    is_internal_transfer,
    reapply_internal_transfer_detection,
)

_TR_BANK_ID = uuid.UUID("6bb6eb78-276d-4b2f-ac63-8eef2c57d307")
_TR_BANK_PARSER_ID = uuid.UUID("1f6a5b19-3b40-4b3e-9a7b-2e0d6f1c9a44")


async def _create_user_with_workspace(email: str, display_name: str = "Test") -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name) "
                "VALUES (:id, :email, 'x', :display_name)"
            ),
            {"id": str(user_id), "email": email, "display_name": display_name},
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


async def _add_member(workspace_id: uuid.UUID, email: str, display_name: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name) "
                "VALUES (:id, :email, 'x', :display_name)"
            ),
            {"id": str(user_id), "email": email, "display_name": display_name},
        )
        # workspace_members_insert richiede "user_id = current_setting(...)
        # AND is_workspace_owner(workspace_id)" (migration 0002) — non esiste
        # un modo legittimo per il proprietario di aggiungere un ALTRO utente
        # come membro sotto RLS (l'app non ha ancora un flusso di invito).
        # Stesso bypass di conftest.py per il reseed delle system category.
        await session.execute(text("SET ROLE lumio_rls_helper"))
        await session.execute(
            text(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES (:w, :u, 'member')"
            ),
            {"w": str(workspace_id), "u": str(user_id)},
        )
        await session.execute(text("RESET ROLE"))
        await session.commit()
    return user_id


async def _create_account(db, workspace_id: uuid.UUID, *, iban: str | None = None) -> uuid.UUID:
    account_id = (
        await db.execute(
            text(
                "INSERT INTO financial_accounts (workspace_id, name, account_type, currency, iban) "
                "VALUES (:w, 'Conto', 'checking', 'EUR', :iban) RETURNING id"
            ),
            {"w": str(workspace_id), "iban": iban},
        )
    ).scalar_one()
    return account_id


# --- is_internal_transfer -------------------------------------------------


async def test_matches_exact_iban_ignoring_case_and_spaces():
    user_id, workspace_id = await _create_user_with_workspace("tr-iban-exact@example.com")
    async with rls_session(user_id) as db:
        await _create_account(db, workspace_id, iban="IT31U0760116700009944199997")
        await db.commit()

    async with rls_session(user_id) as db:
        result = await is_internal_transfer(
            db, workspace_id, TransferCounterparty(name=None, iban="it31 u0760116700009944199997")
        )
    assert result is True


async def test_no_match_for_unknown_iban_and_unknown_name():
    user_id, workspace_id = await _create_user_with_workspace("tr-iban-unknown@example.com")
    async with rls_session(user_id) as db:
        await _create_account(db, workspace_id, iban="IT31U0760116700009944199997")
        await db.commit()

    async with rls_session(user_id) as db:
        result = await is_internal_transfer(
            db, workspace_id, TransferCounterparty(name="Luca Bianchi", iban="IT99Z9999999999999999999999")
        )
    assert result is False


async def test_falls_back_to_name_when_iban_not_registered_on_any_account():
    """L'utente potrebbe non aver ancora compilato l'IBAN del conto — un
    IBAN estratto che non combacia con nessun conto NON deve escludere il
    fallback sul nominativo (deciso esplicitamente con l'utente)."""
    user_id, workspace_id = await _create_user_with_workspace(
        "tr-name-fallback@example.com", display_name="Mario Rossi"
    )
    async with rls_session(user_id) as db:
        await _create_account(db, workspace_id, iban=None)
        await db.commit()

    async with rls_session(user_id) as db:
        result = await is_internal_transfer(
            db, workspace_id, TransferCounterparty(name="Mario Rossi", iban="IT31U0760116700009944199997")
        )
    assert result is True


async def test_name_match_is_case_and_order_insensitive():
    user_id, workspace_id = await _create_user_with_workspace(
        "tr-name-order@example.com", display_name="Mario Rossi"
    )
    async with rls_session(user_id) as db:
        result = await is_internal_transfer(db, workspace_id, TransferCounterparty(name="ROSSI MARIO", iban=None))
    assert result is True


async def test_matches_any_workspace_member_not_only_the_owner():
    user_id, workspace_id = await _create_user_with_workspace(
        "tr-household-owner@example.com", display_name="Mario Rossi"
    )
    await _add_member(workspace_id, "tr-household-partner@example.com", "Giulia Bianchi")

    async with rls_session(user_id) as db:
        result = await is_internal_transfer(db, workspace_id, TransferCounterparty(name="Giulia Bianchi", iban=None))
    assert result is True


async def test_no_match_for_a_different_name():
    user_id, workspace_id = await _create_user_with_workspace(
        "tr-thirdparty@example.com", display_name="Mario Rossi"
    )
    async with rls_session(user_id) as db:
        result = await is_internal_transfer(db, workspace_id, TransferCounterparty(name="Luca Bianchi", iban=None))
    assert result is False


# --- storico IBAN (milestone 09.5c) ---------------------------------------


async def test_matches_a_historical_iban_no_longer_current():
    """Caso reale: un istituto cambia l'IBAN di un conto (es. migrazione
    DE->IT di Trade Republic) — i bonifici storici riportano ancora il
    vecchio IBAN, che deve restare riconoscibile anche se non e' piu'
    quello attuale del conto."""
    user_id, workspace_id = await _create_user_with_workspace("tr-iban-history@example.com")
    async with rls_session(user_id) as db:
        account_id = await _create_account(db, workspace_id, iban="IT31U0760116700001099179999")
        await db.commit()

    async with rls_session(user_id) as db:
        await archive_previous_iban(db, workspace_id, account_id, "DE44500105175407324931")
        await db.commit()

    async with rls_session(user_id) as db:
        result = await is_internal_transfer(
            db, workspace_id, TransferCounterparty(name=None, iban="DE44 5001 0517 5407 3249 31")
        )
    assert result is True


async def test_archive_previous_iban_is_idempotent_no_duplicate_row():
    user_id, workspace_id = await _create_user_with_workspace("tr-iban-archive-idempotent@example.com")
    async with rls_session(user_id) as db:
        account_id = await _create_account(db, workspace_id, iban="IT31U0760116700001099179999")
        await db.commit()

    async with rls_session(user_id) as db:
        await archive_previous_iban(db, workspace_id, account_id, "DE44500105175407324931")
        await archive_previous_iban(db, workspace_id, account_id, "DE44500105175407324931")
        await db.commit()

    async with rls_session(user_id) as db:
        rows = (
            await db.execute(
                select(FinancialAccountIbanHistory).where(
                    FinancialAccountIbanHistory.workspace_id == workspace_id
                )
            )
        ).scalars().all()
    assert len(rows) == 1


# --- reapply_internal_transfer_detection ----------------------------------


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


async def test_reapply_recognizes_transfer_after_iban_is_added_later():
    user_id, workspace_id = await _create_user_with_workspace("tr-reapply@example.com")
    async with rls_session(user_id) as db:
        account_id = await _create_account(db, workspace_id, iban=None)  # IBAN non ancora registrato
        import_id = await _create_pdf_import(db, workspace_id, account_id, user_id)
        txn = Transaction(
            workspace_id=workspace_id,
            financial_account_id=account_id,
            import_id=import_id,
            transaction_date=date(2026, 5, 4),
            description_raw="Incoming transfer for Mario Rossi (IT31U0760116700001099179999)",
            amount="500.00",
            currency="EUR",
            direction="credit",
            transaction_type="income",  # ancora al default: nessuna correzione manuale
            source_type_raw="Bonifico",
            dedup_fingerprint=uuid.uuid4().hex,
        )
        db.add(txn)
        await db.commit()
        txn_id = txn.id

    # L'utente registra ORA l'IBAN del conto (rappresenta se stesso).
    async with rls_session(user_id) as db:
        account = await db.get(FinancialAccount, account_id)
        account.iban = "IT31U0760116700001099179999"
        await db.commit()

    async with rls_session(user_id) as db:
        result = await reapply_internal_transfer_detection(db, workspace_id)
        await db.commit()

    assert result.updated == 1
    assert result.skipped == 0

    async with rls_session(user_id) as db:
        refreshed = await db.get(Transaction, txn_id)
    assert refreshed.transaction_type == "transfer"


async def test_reapply_skips_manually_edited_transactions():
    user_id, workspace_id = await _create_user_with_workspace("tr-reapply-skip@example.com")
    async with rls_session(user_id) as db:
        account_id = await _create_account(db, workspace_id, iban="IT31U0760116700001099179999")
        import_id = await _create_pdf_import(db, workspace_id, account_id, user_id)
        txn = Transaction(
            workspace_id=workspace_id,
            financial_account_id=account_id,
            import_id=import_id,
            transaction_date=date(2026, 5, 4),
            description_raw="Incoming transfer for Mario Rossi (IT31U0760116700001099179999)",
            amount="500.00",
            currency="EUR",
            direction="credit",
            transaction_type="dividend",  # corretta a mano: diverge dal default (income)
            source_type_raw="Bonifico",
            dedup_fingerprint=uuid.uuid4().hex,
        )
        db.add(txn)
        await db.commit()
        txn_id = txn.id

    async with rls_session(user_id) as db:
        result = await reapply_internal_transfer_detection(db, workspace_id)
        await db.commit()

    assert result.updated == 0
    assert result.skipped == 1

    async with rls_session(user_id) as db:
        refreshed = await db.get(Transaction, txn_id)
    assert refreshed.transaction_type == "dividend"

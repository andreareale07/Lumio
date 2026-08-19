"""Transaction Deduplication Engine — test dell'algoritmo (docs/SPEC_DEDUP_TRANSACTION.md).

Pattern "via SQL diretto" (stesso di test_rls_imports.py): workspace/account
creati con INSERT diretti, cosi' i test restano concentrati sull'algoritmo
di `app/services/transaction_dedup.py` senza passare per l'intera pipeline
HTTP/worker (coperta invece da test_transaction_dedup_pipeline.py).
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.db.base import async_session_factory
from app.db.rls import rls_session, set_rls_current_user
from app.models.transaction import Transaction
from app.models.transaction_dedup_decision import TransactionDedupDecision
from app.services.csv_import import ParsedRow
from app.services.transaction_dedup import compute_dedup_fingerprint, run_transaction_dedup

DATE = date(2026, 1, 15)
AMOUNT = Decimal("-42.50")


async def _set_current_user(session, user_id: uuid.UUID) -> None:
    await session.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)})


async def _create_user_with_workspace(email: str) -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            text("INSERT INTO users (id, email, password_hash, display_name) VALUES (:id, :email, 'x', 'Test')"),
            {"id": str(user_id), "email": email},
        )
        await _set_current_user(session, user_id)
        workspace_id = (
            await session.execute(
                text("INSERT INTO workspaces (name, owner_user_id) VALUES ('Personale', :owner) RETURNING id"),
                {"owner": str(user_id)},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (:w, :u, 'owner')"),
            {"w": str(workspace_id), "u": str(user_id)},
        )
        await session.commit()
    return user_id, workspace_id


async def _create_account(user_id: uuid.UUID, workspace_id: uuid.UUID, currency: str = "EUR") -> uuid.UUID:
    async with async_session_factory() as session:
        await _set_current_user(session, user_id)
        account_id = (
            await session.execute(
                text(
                    "INSERT INTO financial_accounts (workspace_id, name, account_type, currency) "
                    "VALUES (:w, 'Conto', 'checking', :c) RETURNING id"
                ),
                {"w": str(workspace_id), "c": currency},
            )
        ).scalar_one()
        await session.commit()
    return account_id


def _row(
    *,
    transaction_date: date = DATE,
    amount: Decimal = AMOUNT,
    currency: str = "EUR",
    description_raw: str = "Netflix",
    description_normalized: str | None = None,
    transaction_type: str = "expense",
    balance_after: Decimal | None = None,
) -> ParsedRow:
    return ParsedRow(
        transaction_date=transaction_date,
        value_date=None,
        description_raw=description_raw,
        description_normalized=description_normalized if description_normalized is not None else description_raw,
        amount=amount,
        currency=currency,
        direction="debit" if amount < 0 else "credit",
        transaction_type=transaction_type,
        reference=None,
        balance_after=balance_after,
    )


async def _seed_existing_transaction(
    session,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    row: ParsedRow,
) -> Transaction:
    fingerprint = compute_dedup_fingerprint(
        workspace_id=workspace_id,
        financial_account_id=account_id,
        transaction_date=row.transaction_date,
        amount=row.amount,
        currency=row.currency,
        description_normalized=row.description_normalized,
        description_raw=row.description_raw,
        transaction_type=row.transaction_type,
    )
    transaction = Transaction(
        workspace_id=workspace_id,
        financial_account_id=account_id,
        transaction_date=row.transaction_date,
        description_raw=row.description_raw,
        description_normalized=row.description_normalized,
        amount=row.amount,
        currency=row.currency,
        direction=row.direction,
        transaction_type=row.transaction_type,
        balance_after=row.balance_after,
        dedup_fingerprint=fingerprint,
    )
    session.add(transaction)
    await session.flush()
    return transaction


async def test_occurrence_matching_two_existing_three_new_is_two_duplicate_one_new():
    """Verifica esplicita richiesta dal piano approvato (§1): 2 occorrenze
    esistenti + 3 nuove identiche -> 2 DUPLICATE + 1 NEW, mai collassate in
    una singola transazione (SPEC §3/§11)."""
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-a@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        await _seed_existing_transaction(session, workspace_id, account_id, _row())
        await _seed_existing_transaction(session, workspace_id, account_id, _row())
        await session.commit()
        await set_rls_current_user(session, user_id)

        rows = [_row(), _row(), _row()]
        result = await run_transaction_dedup(session, workspace_id, account_id, rows)

        assert result.new_count == 1
        assert result.duplicate_count == 2
        assert result.review_count == 0
        assert sorted(o.outcome for o in result.outcomes) == ["duplicate", "duplicate", "new"]


async def test_occurrence_matching_three_existing_two_new_is_two_duplicate_zero_new():
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-b@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        for _ in range(3):
            await _seed_existing_transaction(session, workspace_id, account_id, _row())
        await session.commit()
        await set_rls_current_user(session, user_id)

        result = await run_transaction_dedup(session, workspace_id, account_id, [_row(), _row()])
        assert result.new_count == 0
        assert result.duplicate_count == 2
        assert result.review_count == 0


async def test_description_case_and_whitespace_differences_still_duplicate():
    """SPEC §8: normalizzazione conservativa (NFKC/trim/lowercase/whitespace)
    dedicata al fingerprint — "AMAZON EU SARL" e "amazon   eu sarl" devono
    produrre lo stesso fingerprint."""
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-c@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        await _seed_existing_transaction(
            session, workspace_id, account_id, _row(description_raw="AMAZON EU SARL")
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        result = await run_transaction_dedup(
            session, workspace_id, account_id, [_row(description_raw="amazon   eu   sarl")]
        )
        assert result.duplicate_count == 1
        assert result.new_count == 0


async def test_slightly_different_description_goes_to_review_not_automatic_duplicate():
    """SPEC §5/§35: nessun fuzzy matching aggressivo — una descrizione
    diversa in modo non normalizzabile (stesso conto/data/importo/tipo) deve
    finire in REVIEW, mai risolta automaticamente come duplicato."""
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-d@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        existing = await _seed_existing_transaction(
            session, workspace_id, account_id, _row(description_raw="Amazon EU SARL")
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        result = await run_transaction_dedup(
            session, workspace_id, account_id, [_row(description_raw="Amazon Marketplace")]
        )
        assert result.review_count == 1
        outcome = result.outcomes[0]
        assert outcome.outcome == "review"
        assert outcome.candidate_existing_transaction_id == existing.id
        assert outcome.auto_resolved is False


async def test_different_account_is_never_duplicate():
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-e@example.com")
    account_a = await _create_account(user_id, workspace_id)
    account_b = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        await _seed_existing_transaction(session, workspace_id, account_a, _row())
        await session.commit()
        await set_rls_current_user(session, user_id)

        result = await run_transaction_dedup(session, workspace_id, account_b, [_row()])
        assert result.new_count == 1
        assert result.duplicate_count == 0
        assert result.review_count == 0


async def test_different_workspace_is_never_duplicate():
    user_a, workspace_a = await _create_user_with_workspace("dedup-eng-f-a@example.com")
    user_b, workspace_b = await _create_user_with_workspace("dedup-eng-f-b@example.com")
    account_a = await _create_account(user_a, workspace_a)
    account_b = await _create_account(user_b, workspace_b)

    async with rls_session(user_a) as session:
        await _seed_existing_transaction(session, workspace_a, account_a, _row())
        await session.commit()
        await set_rls_current_user(session, user_a)

    async with rls_session(user_b) as session:
        result = await run_transaction_dedup(session, workspace_b, account_b, [_row()])
        assert result.new_count == 1
        assert result.duplicate_count == 0


def test_fingerprint_differs_by_currency():
    common = dict(
        workspace_id=uuid.uuid4(),
        financial_account_id=uuid.uuid4(),
        transaction_date=DATE,
        amount=AMOUNT,
        description_normalized="netflix",
        description_raw="Netflix",
        transaction_type="expense",
    )
    fp_eur = compute_dedup_fingerprint(**common, currency="EUR")
    fp_usd = compute_dedup_fingerprint(**common, currency="USD")
    assert fp_eur != fp_usd


def test_fingerprint_differs_by_transaction_type():
    common = dict(
        workspace_id=uuid.uuid4(),
        financial_account_id=uuid.uuid4(),
        transaction_date=DATE,
        amount=AMOUNT,
        currency="EUR",
        description_normalized="netflix",
        description_raw="Netflix",
    )
    fp_expense = compute_dedup_fingerprint(**common, transaction_type="expense")
    fp_refund = compute_dedup_fingerprint(**common, transaction_type="refund")
    assert fp_expense != fp_refund


async def test_balance_after_never_changes_the_outcome():
    """Verifica esplicita richiesta dal piano approvato (§5): balance_after
    diverso (o assente) su due transazioni altrimenti identiche non deve
    mai cambiare l'esito NEW/DUPLICATE/REVIEW."""
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-g@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        await _seed_existing_transaction(
            session, workspace_id, account_id, _row(balance_after=Decimal("100.00"))
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        with_balance = await run_transaction_dedup(
            session, workspace_id, account_id, [_row(balance_after=Decimal("999.99"))]
        )
        without_balance = await run_transaction_dedup(
            session, workspace_id, account_id, [_row(balance_after=None)]
        )
        assert with_balance.duplicate_count == without_balance.duplicate_count == 1


async def test_dedup_decision_auto_resolves_confirmed_distinct_without_reproposing_review():
    """Verifica esplicita richiesta dal piano approvato (§2, flusso 'IMPORTA
    COMUNQUE'): una decisione persistita risolve automaticamente lo stesso
    caso in un import successivo, senza tornare in REVIEW."""
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-h@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        existing = await _seed_existing_transaction(
            session, workspace_id, account_id, _row(description_raw="Amazon EU SARL")
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        ambiguous_row = _row(description_raw="Amazon Marketplace")
        first = await run_transaction_dedup(session, workspace_id, account_id, [ambiguous_row])
        assert first.outcomes[0].outcome == "review"
        new_fingerprint = first.outcomes[0].fingerprint

        session.add(
            TransactionDedupDecision(
                workspace_id=workspace_id,
                financial_account_id=account_id,
                existing_transaction_id=existing.id,
                new_fingerprint=new_fingerprint,
                decision="confirmed_distinct",
                decided_by_user_id=user_id,
            )
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        second = await run_transaction_dedup(session, workspace_id, account_id, [ambiguous_row])
        outcome = second.outcomes[0]
        assert outcome.outcome == "new"
        assert outcome.auto_resolved is True
        assert outcome.dedup_decision_id is not None


async def test_dedup_decision_auto_resolves_confirmed_duplicate_without_reproposing_review():
    """Stesso principio, flusso 'NON IMPORTARE': una volta deciso che il
    candidato ambiguo E' lo stesso movimento, i futuri import equivalenti
    devono risultare DUPLICATE senza chiedere di nuovo."""
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-i@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        existing = await _seed_existing_transaction(
            session, workspace_id, account_id, _row(description_raw="Amazon EU SARL")
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        ambiguous_row = _row(description_raw="Amazon Marketplace")
        first = await run_transaction_dedup(session, workspace_id, account_id, [ambiguous_row])
        new_fingerprint = first.outcomes[0].fingerprint

        session.add(
            TransactionDedupDecision(
                workspace_id=workspace_id,
                financial_account_id=account_id,
                existing_transaction_id=existing.id,
                new_fingerprint=new_fingerprint,
                decision="confirmed_duplicate",
                decided_by_user_id=user_id,
            )
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        second = await run_transaction_dedup(session, workspace_id, account_id, [ambiguous_row])
        outcome = second.outcomes[0]
        assert outcome.outcome == "duplicate"
        assert outcome.auto_resolved is True


async def test_confirmed_distinct_decision_never_alters_any_fingerprint():
    """Verifica esplicita richiesta dal piano approvato (§3): la decisione
    e' una relazione persistita, mai una modifica del fingerprint della
    transazione esistente ne' di quello calcolato "a freddo" per la nuova
    riga."""
    user_id, workspace_id = await _create_user_with_workspace("dedup-eng-j@example.com")
    account_id = await _create_account(user_id, workspace_id)

    async with rls_session(user_id) as session:
        existing = await _seed_existing_transaction(
            session, workspace_id, account_id, _row(description_raw="Amazon EU SARL")
        )
        original_existing_fingerprint = existing.dedup_fingerprint
        await session.commit()
        await set_rls_current_user(session, user_id)

        ambiguous_row = _row(description_raw="Amazon Marketplace")
        first = await run_transaction_dedup(session, workspace_id, account_id, [ambiguous_row])
        new_fingerprint = first.outcomes[0].fingerprint

        session.add(
            TransactionDedupDecision(
                workspace_id=workspace_id,
                financial_account_id=account_id,
                existing_transaction_id=existing.id,
                new_fingerprint=new_fingerprint,
                decision="confirmed_distinct",
                decided_by_user_id=user_id,
            )
        )
        await session.commit()
        await set_rls_current_user(session, user_id)

        recomputed_new_fingerprint = compute_dedup_fingerprint(
            workspace_id=workspace_id,
            financial_account_id=account_id,
            transaction_date=ambiguous_row.transaction_date,
            amount=ambiguous_row.amount,
            currency=ambiguous_row.currency,
            description_normalized=ambiguous_row.description_normalized,
            description_raw=ambiguous_row.description_raw,
            transaction_type=ambiguous_row.transaction_type,
        )
        assert new_fingerprint == recomputed_new_fingerprint
        assert existing.dedup_fingerprint == original_existing_fingerprint

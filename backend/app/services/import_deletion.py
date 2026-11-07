"""Eliminazione delle transazioni di un import e delle loro dipendenze.

Estratta da `DELETE /imports/{id}` (`app/api/v1/imports.py`) per essere
condivisa con lo scollegamento di una banca Open Banking quando l'utente chiede
di eliminare anche i movimenti importati: la regola e' una sola, non duplicata.
Non fa commit e non elimina la riga `imports` (lo decide il chiamante).
"""
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_ import Import
from app.models.investment_transaction import InvestmentTransaction
from app.models.open_banking import BankConnectionAccount, BankTransactionTombstone
from app.models.transaction import Transaction
from app.services.position_service import recompute_position


async def reset_open_banking_cursor(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    *,
    zero_counter: bool = False,
    clear_tombstones: bool = False,
) -> None:
    """Fa ripartire la sync Open Banking dei conti bancari abbinati al conto Lumio.

    Il cursore (`last_booked_date`) deve sempre rispecchiare cio' che e' davvero
    nel database: dopo l'eliminazione di un import (o il cambio/eliminazione del
    conto abbinato) la prossima sync deve rileggere tutto lo storico (`longest`);
    il dedup assorbe cio' che esiste ancora. `zero_counter` azzera il contatore
    (conto cambiato o eliminato), altrimenti lo ricalcola dagli import
    open_banking rimasti. `clear_tombstones` svuota anche i movimenti eliminati
    a mano ("Rileggi storico" li fa tornare).

    La tabella dei conti bancari e' owner-only: se la connessione e' di un altro
    membro del workspace la RLS non mostra la riga e l'UPDATE non la tocca. Non
    fa commit.
    """
    remaining = 0
    if not zero_counter:
        remaining = (
            await db.scalar(
                select(func.coalesce(func.sum(Import.transactions_imported), 0)).where(
                    Import.workspace_id == workspace_id,
                    Import.financial_account_id == financial_account_id,
                    Import.file_type == "open_banking",
                )
            )
        ) or 0
    await db.execute(
        update(BankConnectionAccount)
        .where(
            BankConnectionAccount.workspace_id == workspace_id,
            BankConnectionAccount.financial_account_id == financial_account_id,
        )
        .values(last_booked_date=None, transactions_imported=remaining)
    )
    if clear_tombstones:
        await db.execute(
            delete(BankTransactionTombstone).where(
                BankTransactionTombstone.workspace_id == workspace_id,
                BankTransactionTombstone.financial_account_id == financial_account_id,
            )
        )


async def delete_import_transactions(db: AsyncSession, workspace_id: uuid.UUID, import_id: uuid.UUID) -> int:
    """Ritorna il numero di transazioni eliminate."""
    # Scoperto su dati reali (import PDF Trade Republic con
    # investment_transactions collegate via transaction_id, M09.5c): cancellare
    # a ritroso, MAI allargare i vincoli — le righe dipendenti vanno rimosse
    # (o scollegate, se non devono sparire) PRIMA della riga padre, cosi'
    # nessuna delete successiva viola mai un vincolo.
    #
    # `source_type_raw` distingue le due categorie (mai popolato da un
    # inserimento manuale, vedi commento su InvestmentTransactionCreate):
    # - auto-creato dal parser durante l'import (source_type_raw NOT NULL):
    #   e' conseguenza dell'import stesso — si cancella per intero, poi si
    #   ricalcola la posizione (asset, conto) coinvolta, stesso servizio
    #   usato da DELETE /investment-transactions/{id}.
    # - inserito/collegato a mano dall'utente (source_type_raw NULL): resta
    #   dato reale dell'utente, NON creato da questo import — si scollega
    #   solo il riferimento alla transazione in via di cancellazione, la riga
    #   stessa non si tocca.
    linked_result = await db.execute(
        select(InvestmentTransaction).where(
            InvestmentTransaction.workspace_id == workspace_id,
            InvestmentTransaction.transaction_id.in_(
                select(Transaction.id).where(
                    Transaction.workspace_id == workspace_id, Transaction.import_id == import_id
                )
            ),
        )
    )
    linked_investment_transactions = list(linked_result.scalars().all())

    positions_to_recompute: set[tuple[uuid.UUID, uuid.UUID, str]] = set()
    for investment_txn in linked_investment_transactions:
        if investment_txn.source_type_raw is not None:
            if investment_txn.asset_id is not None:
                positions_to_recompute.add(
                    (investment_txn.financial_account_id, investment_txn.asset_id, investment_txn.currency)
                )
            await db.delete(investment_txn)
        else:
            investment_txn.transaction_id = None
    await db.flush()

    for account_id, asset_id, currency in positions_to_recompute:
        await recompute_position(db, workspace_id, account_id, asset_id, currency)

    delete_result = await db.execute(
        delete(Transaction).where(
            Transaction.workspace_id == workspace_id, Transaction.import_id == import_id
        )
    )
    deleted_count = delete_result.rowcount
    return deleted_count

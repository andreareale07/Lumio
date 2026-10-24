"""Logica DB-aware delle posizioni (SPEC §34), ponte tra l'API
(`app/api/v1/investment_transactions.py`, `app/api/v1/positions.py`) e il
libro mastro `InvestmentTransaction` — stessa separazione DB-aware/pura di
`analytics.py`/`analytics_calc.py`.

`positions` non ha MAI una via di scrittura propria indipendente dai
movimenti: ogni funzione che tocca `investment_transactions` (create/update/
delete) chiama `recompute_position` subito dopo, nella stessa transazione
DB. La "modifica manuale di una posizione" (SPEC, decisione M09) non e' un
UPDATE diretto su `positions`: e' un movimento `adjustment` che codifica il
delta, cosi' resta un'unica sorgente di verita' auditabile.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.financial_account import FinancialAccount
from app.models.investment_transaction import InvestmentTransaction
from app.models.position import Position
from app.services.position_calc import compute_position


async def recompute_position(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    asset_id: uuid.UUID,
    currency: str,
) -> tuple[Position | None, list[str]]:
    """Rilegge TUTTI i movimenti di (conto, asset) e riscrive la riga
    `positions` corrispondente. Idempotente: puo' essere chiamata piu' volte
    di seguito senza effetti collaterali diversi. Ritorna `(None, [])` se
    non esiste nessun movimento per questa coppia (nessuna riga da creare —
    evita posizioni "fantasma" a zero senza storia)."""
    result = await db.execute(
        select(InvestmentTransaction)
        .where(
            InvestmentTransaction.workspace_id == workspace_id,
            InvestmentTransaction.financial_account_id == financial_account_id,
            InvestmentTransaction.asset_id == asset_id,
        )
        # Ordine deterministico anche con piu' movimenti nello stesso
        # giorno, stesso principio dell'ancora+delta di analytics.py.
        .order_by(
            InvestmentTransaction.trade_date,
            InvestmentTransaction.created_at,
            InvestmentTransaction.id,
        )
    )
    movements = list(result.scalars().all())
    if not movements:
        existing = await db.execute(
            select(Position).where(
                Position.workspace_id == workspace_id,
                Position.financial_account_id == financial_account_id,
                Position.asset_id == asset_id,
            )
        )
        position = existing.scalar_one_or_none()
        if position is not None:
            await db.delete(position)
        return None, []

    state = compute_position(movements)

    result = await db.execute(
        select(Position).where(
            Position.workspace_id == workspace_id,
            Position.financial_account_id == financial_account_id,
            Position.asset_id == asset_id,
        )
    )
    position = result.scalar_one_or_none()
    if position is None:
        position = Position(
            workspace_id=workspace_id,
            financial_account_id=financial_account_id,
            asset_id=asset_id,
            currency=currency,
        )
        db.add(position)

    # Quantizzazione alla scala della colonna: normalizza l'esponente per
    # coerenza (es. dopo uno split che introduce divisioni). NON risolve da
    # sola il caso "posizione chiusa esattamente" (Decimal a coefficiente
    # zero con esponente <= -7 usa notazione scientifica nel suo `str()`
    # A PRESCINDERE da quantize/normalize — verificato empiricamente): quel
    # caso e' gestito al momento della serializzazione API, vedi
    # `app/schemas/decimal_fields.py` e `PositionOut`.
    position.quantity = state.quantity.quantize(Decimal("1.0000000000"))
    position.average_cost = state.average_cost.quantize(Decimal("1.000000"))
    position.realized_pl = state.realized_pl.quantize(Decimal("1.00"))
    position.currency = currency

    # Flush + refresh QUI, dentro la stessa transazione (RLS ancora valida,
    # SET LOCAL scade solo al commit — vedi lumio-rls-gotchas): senza questo,
    # un chiamante che ritorna `position` direttamente al client (per evitare
    # la query-dopo-commit, vedi apply_manual_position_edit) esporrebbe il
    # Decimal Python non normalizzato (es. "120" invece di "120.0000000000")
    # invece del valore effettivamente scritto da Postgres, che applica la
    # scala NUMERIC(28,10)/NUMERIC(18,6) della colonna.
    await db.flush()
    await db.refresh(position)
    return position, state.warnings


async def apply_manual_position_edit(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    asset_id: uuid.UUID,
    currency: str,
    target_quantity: Decimal,
    target_average_cost: Decimal,
    notes: str | None = None,
) -> Position:
    """Modifica manuale di una posizione (SPEC, decisione M09): l'utente
    digita direttamente quantita'/costo medio desiderati; qui si calcola il
    DELTA rispetto allo stato derivato attuale e si scrive un movimento
    `adjustment` — mai un UPDATE diretto su `positions` (vedi docstring di
    modulo). Il chiamante e' responsabile del commit.

    Ritorna la `Position` risultante (istanza gia' in sessione, NON
    ricaricata con una query dopo il commit del chiamante): `SET LOCAL
    app.current_user_id` scade al commit (vedi lumio-rls-gotchas), quindi
    una SELECT successiva al commit gira senza identita' RLS valida e
    `is_workspace_member()` fallisce il cast a uuid su stringa vuota — stesso
    principio di `activate_profile` in `ai_profile_service.py`: si riusa
    l'oggetto in memoria, mai una query di refresh post-commit.
    """
    position, _ = await recompute_position(db, workspace_id, financial_account_id, asset_id, currency)
    current_quantity = position.quantity if position is not None else Decimal("0")
    delta = target_quantity - current_quantity

    adjustment = InvestmentTransaction(
        workspace_id=workspace_id,
        financial_account_id=financial_account_id,
        asset_id=asset_id,
        trade_date=date.today(),
        type="adjustment",
        quantity=delta,
        price=target_average_cost,
        amount=Decimal("0"),
        currency=currency,
        notes=notes,
    )
    db.add(adjustment)
    await db.flush()
    position, _ = await recompute_position(db, workspace_id, financial_account_id, asset_id, currency)
    assert position is not None  # l'adjustment appena aggiunto rende i movimenti non vuoti
    return position


@dataclass(frozen=True)
class PositionChange:
    asset_name: str
    account_name: str
    currency: str
    financial_account_id: uuid.UUID
    old_quantity: Decimal | None
    new_quantity: Decimal
    old_average_cost: Decimal | None
    new_average_cost: Decimal
    old_realized_pl: Decimal | None
    new_realized_pl: Decimal


@dataclass(frozen=True)
class RecomputeReport:
    checked: int
    changes: list[PositionChange]


async def recompute_all_positions(db: AsyncSession, workspace_id: uuid.UUID) -> RecomputeReport:
    """Ricalcola dai movimenti TUTTE le posizioni del workspace (riparazione
    dopo un fix al calcolo: `positions` e' un valore salvato, si aggiorna solo
    quando un suo movimento cambia). Il report elenca solo le posizioni il cui
    valore salvato e' effettivamente cambiato. Nessun commit: lo fa il
    chiamante (che puo' anche scartare tutto, per un'anteprima)."""
    keys = (
        await db.execute(
            select(
                InvestmentTransaction.financial_account_id,
                InvestmentTransaction.asset_id,
                InvestmentTransaction.currency,
            )
            .where(InvestmentTransaction.workspace_id == workspace_id, InvestmentTransaction.asset_id.is_not(None))
            .distinct()
        )
    ).all()
    asset_names = {
        a.id: a.name
        for a in (await db.execute(select(Asset).where(Asset.workspace_id == workspace_id))).scalars().all()
    }
    account_names = {
        a.id: a.name
        for a in (
            await db.execute(select(FinancialAccount).where(FinancialAccount.workspace_id == workspace_id))
        )
        .scalars()
        .all()
    }

    changes: list[PositionChange] = []
    for account_id, asset_id, currency in keys:
        existing = (
            await db.execute(
                select(Position).where(
                    Position.workspace_id == workspace_id,
                    Position.financial_account_id == account_id,
                    Position.asset_id == asset_id,
                )
            )
        ).scalar_one_or_none()
        before = (
            (existing.quantity, existing.average_cost, existing.realized_pl) if existing is not None else None
        )
        position, _ = await recompute_position(db, workspace_id, account_id, asset_id, currency)
        if position is None:
            continue
        after = (position.quantity, position.average_cost, position.realized_pl)
        if before == after:
            continue
        changes.append(
            PositionChange(
                asset_name=asset_names.get(asset_id, str(asset_id)),
                account_name=account_names.get(account_id, str(account_id)),
                currency=currency,
                financial_account_id=account_id,
                old_quantity=before[0] if before else None,
                new_quantity=after[0],
                old_average_cost=before[1] if before else None,
                new_average_cost=after[1],
                old_realized_pl=before[2] if before else None,
                new_realized_pl=after[2],
            )
        )
    return RecomputeReport(checked=len(keys), changes=changes)

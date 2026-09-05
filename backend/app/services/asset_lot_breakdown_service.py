"""Scomposizione aperto/chiuso per singolo asset (feature portfolio, non
fiscale — riusa il motore a lotti gia' costruito per FETTA 2 perche' e'
esattamente lo stesso problema: "quale acquisto ha chiuso quale vendita").

Nato da un bug reale segnalato dall'utente: la tabella "Acquisti" di
`AssetDetailPage` calcolava il rendimento di OGNI riga contro il prezzo
ATTUALE, anche per posizioni gia' vendute — un numero senza senso per una
posizione chiusa. Qui si scompone ogni acquisto in una parte REALIZZATA
(venduta, contro il prezzo vero di vendita) e una parte ANCORA APERTA
(contro il prezzo attuale, calcolato lato frontend che gia' lo possiede).

Il criterio di consumo (LIFO/FIFO) e' risolto dalla giurisdizione fiscale
corrente (`resolve_tax_context` + `TaxRuleset.lot_consumption_order`), non
un valore fisso — coerente con l'architettura di TaxJurisdiction: se domani
un'altra giurisdizione usasse FIFO, questa pagina lo seguirebbe senza
modifiche (richiesta esplicita dell'utente)."""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment_transaction import InvestmentTransaction
from app.services.tax_context import resolve_tax_context
from app.services.tax_lot_calc import compute_tax_lots


@dataclass(frozen=True)
class ClosedPortion:
    quantity: Decimal
    sell_transaction_id: uuid.UUID
    sell_trade_date: date
    proceeds: Decimal
    cost_basis: Decimal
    gain_or_loss: Decimal


@dataclass(frozen=True)
class LotBreakdownRow:
    transaction_id: uuid.UUID
    financial_account_id: uuid.UUID
    trade_date: date
    quantity: Decimal  # quantita' originale registrata sul movimento di acquisto
    price: Decimal
    open_quantity: Decimal  # quanto di questo lotto e' ancora posseduto
    closed_portions: tuple[ClosedPortion, ...]


async def compute_lot_breakdown(
    db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID, on: date
) -> list[LotBreakdownRow]:
    context = await resolve_tax_context(db, workspace_id, on)
    consumption_order = context.jurisdiction.ruleset_at(on).lot_consumption_order

    result = await db.execute(
        select(InvestmentTransaction)
        .where(
            InvestmentTransaction.workspace_id == workspace_id,
            InvestmentTransaction.asset_id == asset_id,
            InvestmentTransaction.type.in_(("buy", "sell", "opening", "split", "adjustment", "dividend")),
        )
        .order_by(
            InvestmentTransaction.financial_account_id,
            InvestmentTransaction.trade_date,
            InvestmentTransaction.created_at,
            InvestmentTransaction.id,
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return []

    groups: dict[uuid.UUID, list[InvestmentTransaction]] = {}
    for row in rows:
        groups.setdefault(row.financial_account_id, []).append(row)

    breakdown: list[LotBreakdownRow] = []
    for account_id, movements in groups.items():
        state = compute_tax_lots(movements, consumption_order)

        # Movimenti che hanno creato un lotto (acquisti reali + adjustment
        # positivi con prezzo — stesso elenco di casi gestiti in
        # tax_lot_calc.compute_tax_lots per il ramo "creazione lotto").
        lot_sources = {
            m.id: m
            for m in movements
            if m.type in ("buy", "opening")
            or (m.type == "adjustment" and (m.quantity or Decimal("0")) > 0 and m.price is not None)
        }

        closed_by_lot: dict[uuid.UUID, list[ClosedPortion]] = {}
        for event in state.realized_events:
            closed_by_lot.setdefault(event.lot_transaction_id, []).append(
                ClosedPortion(
                    quantity=event.quantity,
                    sell_transaction_id=event.sell_transaction_id,
                    sell_trade_date=event.trade_date,
                    proceeds=event.proceeds,
                    cost_basis=event.cost_basis,
                    gain_or_loss=event.gain_or_loss,
                )
            )
        open_by_lot: dict[uuid.UUID, Decimal] = {lot.transaction_id: lot.quantity for lot in state.open_lots}

        for transaction_id, source in lot_sources.items():
            breakdown.append(
                LotBreakdownRow(
                    transaction_id=transaction_id,
                    financial_account_id=account_id,
                    trade_date=source.trade_date,
                    quantity=source.quantity or Decimal("0"),
                    price=source.price or Decimal("0"),
                    open_quantity=open_by_lot.get(transaction_id, Decimal("0")),
                    closed_portions=tuple(closed_by_lot.get(transaction_id, [])),
                )
            )

    return sorted(breakdown, key=lambda r: r.trade_date)

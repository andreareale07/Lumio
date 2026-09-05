"""Override utente di un evento realizzato specifico (FETTA 2). Un evento
e' identificato dalla coppia `(lot_transaction_id, sell_transaction_id)`,
univoca per costruzione (vedi `app/models/tax_realized_event_override.py`).
Nessun commit qui — il chiamante decide il confine di transazione, stesso
principio degli altri servizi fiscali."""
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_realized_event_override import TaxRealizedEventOverride


async def list_overrides(db: AsyncSession, workspace_id: uuid.UUID) -> list[TaxRealizedEventOverride]:
    result = await db.execute(
        select(TaxRealizedEventOverride).where(TaxRealizedEventOverride.workspace_id == workspace_id)
    )
    return list(result.scalars().all())


async def get_override(
    db: AsyncSession, workspace_id: uuid.UUID, lot_transaction_id: uuid.UUID, sell_transaction_id: uuid.UUID
) -> TaxRealizedEventOverride | None:
    result = await db.execute(
        select(TaxRealizedEventOverride).where(
            TaxRealizedEventOverride.workspace_id == workspace_id,
            TaxRealizedEventOverride.lot_transaction_id == lot_transaction_id,
            TaxRealizedEventOverride.sell_transaction_id == sell_transaction_id,
        )
    )
    return result.scalar_one_or_none()


async def set_override(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lot_transaction_id: uuid.UUID,
    sell_transaction_id: uuid.UUID,
    override_gain_or_loss: Decimal | None,
    excluded: bool,
    notes: str | None,
) -> TaxRealizedEventOverride:
    override = await get_override(db, workspace_id, lot_transaction_id, sell_transaction_id)
    if override is None:
        override = TaxRealizedEventOverride(
            workspace_id=workspace_id,
            lot_transaction_id=lot_transaction_id,
            sell_transaction_id=sell_transaction_id,
        )
        db.add(override)
    override.override_gain_or_loss = override_gain_or_loss
    override.excluded = excluded
    override.notes = notes
    await db.flush()
    return override


async def delete_override(
    db: AsyncSession, workspace_id: uuid.UUID, lot_transaction_id: uuid.UUID, sell_transaction_id: uuid.UUID
) -> None:
    override = await get_override(db, workspace_id, lot_transaction_id, sell_transaction_id)
    if override is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun override per questo evento")
    await db.delete(override)
    await db.flush()

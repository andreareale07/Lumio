"""CRUD dei saldi di apertura dello zainetto fiscale (SPEC_TAX_REGIME.md
FETTA 1) — unica fonte che alimenta `tax_calc.build_loss_pocket` in questa
fetta. Il vincolo "regime dichiarativo <-> financial_account_id NULL, regime
amministrato <-> financial_account_id valorizzato" non e' esprimibile in DB
(dipende dal `pocket_scope` del regime, dato in codice in `app/tax/`):
enforced qui con 400 esplicito, mai delegato a un CHECK constraint."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_loss_opening_balance import TaxLossOpeningBalance
from app.services.tax_regime_service import resolve_regime_at
from app.tax.base import TaxJurisdiction


async def _validate_perimeter(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    financial_account_id: uuid.UUID | None,
    formation_date: date,
) -> None:
    if financial_account_id is None:
        # Perimetro dichiarativo aggregato: nessun conto specifico da
        # verificare, e' per costruzione personale/aggregato.
        return

    regime_code = await resolve_regime_at(db, workspace_id, financial_account_id, formation_date)
    if regime_code is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nessun regime fiscale impostato per questo conto alla data di formazione",
        )
    regime = next((r for r in jurisdiction.regimes(formation_date) if r.code == regime_code), None)
    if regime is None or regime.pocket_scope != "per_account":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Il conto non e' in un regime a perimetro per-intermediario a questa data: "
            "un'apertura con conto valorizzato richiede un regime amministrato (o equivalente)",
        )


async def list_openings(db: AsyncSession, workspace_id: uuid.UUID) -> list[TaxLossOpeningBalance]:
    result = await db.execute(
        select(TaxLossOpeningBalance)
        .where(TaxLossOpeningBalance.workspace_id == workspace_id)
        .order_by(TaxLossOpeningBalance.financial_account_id, TaxLossOpeningBalance.formation_date)
    )
    return list(result.scalars().all())


async def create_opening(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    financial_account_id: uuid.UUID | None,
    formation_date: date,
    income_category: str,
    amount: Decimal,
) -> TaxLossOpeningBalance:
    await _validate_perimeter(db, workspace_id, jurisdiction, financial_account_id, formation_date)
    formed_under_ruleset_code = jurisdiction.ruleset_at(formation_date).code

    opening = TaxLossOpeningBalance(
        workspace_id=workspace_id,
        financial_account_id=financial_account_id,
        formation_date=formation_date,
        formed_under_ruleset_code=formed_under_ruleset_code,
        income_category=income_category,
        amount=amount,
    )
    db.add(opening)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esiste gia' un saldo di apertura per questo perimetro e data di formazione",
        ) from exc
    return opening


async def update_opening(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    opening_id: uuid.UUID,
    formation_date: date | None,
    income_category: str | None,
    amount: Decimal | None,
) -> TaxLossOpeningBalance:
    opening = await _get_opening_or_404(db, workspace_id, opening_id)
    new_formation_date = formation_date if formation_date is not None else opening.formation_date
    if formation_date is not None:
        await _validate_perimeter(
            db, workspace_id, jurisdiction, opening.financial_account_id, new_formation_date
        )
        opening.formed_under_ruleset_code = jurisdiction.ruleset_at(new_formation_date).code
    opening.formation_date = new_formation_date
    if income_category is not None:
        opening.income_category = income_category
    if amount is not None:
        opening.amount = amount

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esiste gia' un saldo di apertura per questo perimetro e data di formazione",
        ) from exc
    return opening


async def delete_opening(db: AsyncSession, workspace_id: uuid.UUID, opening_id: uuid.UUID) -> None:
    opening = await _get_opening_or_404(db, workspace_id, opening_id)
    await db.delete(opening)
    await db.flush()


async def _get_opening_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, opening_id: uuid.UUID
) -> TaxLossOpeningBalance:
    opening = await db.get(TaxLossOpeningBalance, opening_id)
    if opening is None or opening.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saldo di apertura non trovato")
    return opening

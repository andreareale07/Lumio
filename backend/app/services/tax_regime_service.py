"""CRUD dei periodi di regime fiscale di un conto + risoluzione a data
(SPEC_TAX_REGIME.md FETTA 1). Nessun commit qui — il chiamante (endpoint)
decide il confine di transazione, stesso principio di `account_service.py`.

Caso canonico: un conto Trade Republic con due periodi consecutivi
(dichiarativo fino al cambio IBAN, amministrato dopo) — l'intervallo di ogni
riga e' `[effective_from, next.effective_from)`, mai un `valid_to` esplicito
(append-only, stesso pattern minimo di `financial_account_iban_history`)."""
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_account_tax_regime import FinancialAccountTaxRegime
from app.tax.base import TaxJurisdiction


def _validate_regime_code(jurisdiction: TaxJurisdiction, regime_code: str, effective_from: date) -> None:
    valid_codes = {r.code for r in jurisdiction.regimes(effective_from)}
    if regime_code not in valid_codes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"regime_code {regime_code!r} non ammesso da {jurisdiction.code} al {effective_from.isoformat()}",
        )


async def list_regime_periods(
    db: AsyncSession, workspace_id: uuid.UUID, financial_account_id: uuid.UUID
) -> list[FinancialAccountTaxRegime]:
    result = await db.execute(
        select(FinancialAccountTaxRegime)
        .where(
            FinancialAccountTaxRegime.workspace_id == workspace_id,
            FinancialAccountTaxRegime.financial_account_id == financial_account_id,
        )
        .order_by(FinancialAccountTaxRegime.effective_from)
    )
    return list(result.scalars().all())


async def resolve_regime_at(
    db: AsyncSession, workspace_id: uuid.UUID, financial_account_id: uuid.UUID, on: date
) -> str | None:
    result = await db.execute(
        select(FinancialAccountTaxRegime.regime_code)
        .where(
            FinancialAccountTaxRegime.workspace_id == workspace_id,
            FinancialAccountTaxRegime.financial_account_id == financial_account_id,
            FinancialAccountTaxRegime.effective_from <= on,
        )
        .order_by(FinancialAccountTaxRegime.effective_from.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_regime_period(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    regime_code: str,
    effective_from: date,
) -> FinancialAccountTaxRegime:
    _validate_regime_code(jurisdiction, regime_code, effective_from)
    period = FinancialAccountTaxRegime(
        workspace_id=workspace_id,
        financial_account_id=financial_account_id,
        regime_code=regime_code,
        effective_from=effective_from,
    )
    db.add(period)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esiste gia' un periodo di regime con questa effective_from"
        ) from exc
    return period


async def update_regime_period(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    financial_account_id: uuid.UUID,
    period_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    regime_code: str | None,
    effective_from: date | None,
) -> FinancialAccountTaxRegime:
    period = await _get_period_or_404(db, workspace_id, financial_account_id, period_id)
    new_effective_from = effective_from if effective_from is not None else period.effective_from
    new_regime_code = regime_code if regime_code is not None else period.regime_code
    _validate_regime_code(jurisdiction, new_regime_code, new_effective_from)
    period.regime_code = new_regime_code
    period.effective_from = new_effective_from
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esiste gia' un periodo di regime con questa effective_from"
        ) from exc
    return period


async def delete_regime_period(
    db: AsyncSession, workspace_id: uuid.UUID, financial_account_id: uuid.UUID, period_id: uuid.UUID
) -> None:
    period = await _get_period_or_404(db, workspace_id, financial_account_id, period_id)
    await db.delete(period)
    await db.flush()


async def _get_period_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, financial_account_id: uuid.UUID, period_id: uuid.UUID
) -> FinancialAccountTaxRegime:
    period = await db.get(FinancialAccountTaxRegime, period_id)
    if (
        period is None
        or period.workspace_id != workspace_id
        or period.financial_account_id != financial_account_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Periodo di regime non trovato")
    return period

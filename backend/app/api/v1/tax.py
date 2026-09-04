"""API fiscale (SPEC_TAX_REGIME.md FETTA 1). Router dedicato (non
sotto-risorsa di `accounts`): la fiscalita' attraversa conti, asset e
impostazioni, un'unica risorsa `/tax` evita di forzare l'accoppiamento in
una delle tre."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_workspace_id
from app.db.session import get_db
from app.models.financial_account import FinancialAccount
from app.models.user import User
from app.models.workspace_tax_residence import WorkspaceTaxResidence
from app.schemas.tax import (
    AssetTaxClassificationOut,
    AssetTaxClassificationSetIn,
    CarryForwardRuleOut,
    LossConversionOut,
    LossPocketOut,
    LossPocketRowOut,
    OffsetRuleOut,
    TaxAssetClassOut,
    TaxJurisdictionOut,
    TaxLossOpeningCreate,
    TaxLossOpeningOut,
    TaxLossOpeningUpdate,
    TaxRegimeOptionOut,
    TaxRegimePeriodCreate,
    TaxRegimePeriodOut,
    TaxRegimePeriodUpdate,
    TaxRegimeResolveOut,
    TaxRulesetDetailOut,
    TaxRulesetSummaryOut,
    TaxTreatmentOut,
    WorkspaceTaxResidenceIn,
    WorkspaceTaxResidenceOut,
)
from app.services import tax_classification_service, tax_opening_service, tax_regime_service
from app.services.audit_log_service import log_event
from app.services.tax_calc import LossPocketEntry, build_loss_pocket
from app.services.tax_context import resolve_tax_context
from app.tax.registry import JURISDICTIONS, get_jurisdiction

router = APIRouter(prefix="/tax", tags=["tax"])


def _ruleset_detail(jurisdiction, ruleset, on: date) -> TaxRulesetDetailOut:
    return TaxRulesetDetailOut(
        code=ruleset.code,
        valid_from=ruleset.valid_from,
        valid_until=ruleset.valid_until,
        treatments=[TaxTreatmentOut(**vars(t)) for t in ruleset.treatments],
        offset_rules=[OffsetRuleOut(**vars(r)) for r in ruleset.offset_rules],
        carry_forward=CarryForwardRuleOut(**vars(ruleset.carry_forward)),
        loss_conversions=[LossConversionOut(**vars(c)) for c in ruleset.loss_conversions],
        regimes=[TaxRegimeOptionOut(**vars(r)) for r in jurisdiction.regimes(on)],
        asset_classes=[TaxAssetClassOut(**vars(c)) for c in jurisdiction.tax_asset_classes(on)],
    )


async def _get_account_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> FinancialAccount:
    account = await db.get(FinancialAccount, account_id)
    if account is None or account.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conto non trovato")
    return account


# --- Regolamento (letto da app/tax/, mai da DB) ------------------------------


@router.get("/jurisdictions", response_model=list[TaxJurisdictionOut])
async def list_jurisdictions() -> list[TaxJurisdictionOut]:
    return [TaxJurisdictionOut(code=j.code, label_key=j.label_key) for j in JURISDICTIONS]


@router.get("/rulesets", response_model=list[TaxRulesetSummaryOut])
async def list_rulesets(
    jurisdiction_code: str = Query(default="IT"),
) -> list[TaxRulesetSummaryOut]:
    jurisdiction = get_jurisdiction(jurisdiction_code)
    return [
        TaxRulesetSummaryOut(code=r.code, valid_from=r.valid_from, valid_until=r.valid_until)
        for r in jurisdiction.rulesets()
    ]


@router.get("/ruleset", response_model=TaxRulesetDetailOut)
async def get_ruleset_at(
    on: date = Query(),
    jurisdiction_code: str = Query(default="IT"),
) -> TaxRulesetDetailOut:
    jurisdiction = get_jurisdiction(jurisdiction_code)
    return _ruleset_detail(jurisdiction, jurisdiction.ruleset_at(on), on)


# --- Residenza fiscale --------------------------------------------------------


@router.get("/residences", response_model=list[WorkspaceTaxResidenceOut])
async def list_residences(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceTaxResidenceOut]:
    result = await db.execute(
        select(WorkspaceTaxResidence)
        .where(WorkspaceTaxResidence.workspace_id == workspace_id)
        .order_by(WorkspaceTaxResidence.fiscal_year)
    )
    return list(result.scalars().all())


@router.put("/residences/{fiscal_year}", response_model=WorkspaceTaxResidenceOut)
async def upsert_residence(
    fiscal_year: int,
    payload: WorkspaceTaxResidenceIn,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceTaxResidenceOut:
    if payload.fiscal_year != fiscal_year:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "fiscal_year nel path e nel body non coincidono")
    get_jurisdiction(payload.jurisdiction_code)  # 404-equivalente: ValueError se sconosciuta

    result = await db.execute(
        select(WorkspaceTaxResidence).where(
            WorkspaceTaxResidence.workspace_id == workspace_id,
            WorkspaceTaxResidence.fiscal_year == fiscal_year,
        )
    )
    residence = result.scalar_one_or_none()
    if residence is None:
        residence = WorkspaceTaxResidence(
            workspace_id=workspace_id, fiscal_year=fiscal_year, jurisdiction_code=payload.jurisdiction_code
        )
        db.add(residence)
    else:
        residence.jurisdiction_code = payload.jurisdiction_code

    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="workspace_tax_residence", metadata={"fiscal_year": fiscal_year},
    )
    await db.commit()
    return residence


@router.delete("/residences/{fiscal_year}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_residence(
    fiscal_year: int,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(WorkspaceTaxResidence).where(
            WorkspaceTaxResidence.workspace_id == workspace_id,
            WorkspaceTaxResidence.fiscal_year == fiscal_year,
        )
    )
    residence = result.scalar_one_or_none()
    if residence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Residenza non trovata per questo anno")
    await db.delete(residence)
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="workspace_tax_residence", metadata={"fiscal_year": fiscal_year, "deleted": True},
    )
    await db.commit()


# --- Regimi del conto ---------------------------------------------------------


@router.get("/accounts/{account_id}/regimes", response_model=list[TaxRegimePeriodOut])
async def list_account_regimes(
    account_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[TaxRegimePeriodOut]:
    await _get_account_or_404(db, workspace_id, account_id)
    return await tax_regime_service.list_regime_periods(db, workspace_id, account_id)


@router.post("/accounts/{account_id}/regimes", response_model=TaxRegimePeriodOut, status_code=status.HTTP_201_CREATED)
async def create_account_regime(
    account_id: uuid.UUID,
    payload: TaxRegimePeriodCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaxRegimePeriodOut:
    await _get_account_or_404(db, workspace_id, account_id)
    context = await resolve_tax_context(db, workspace_id, payload.effective_from)
    period = await tax_regime_service.create_regime_period(
        db, workspace_id, account_id, context.jurisdiction, payload.regime_code, payload.effective_from
    )
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="financial_account_tax_regime", entity_id=period.id,
    )
    await db.commit()
    return period


@router.patch("/accounts/{account_id}/regimes/{period_id}", response_model=TaxRegimePeriodOut)
async def update_account_regime(
    account_id: uuid.UUID,
    period_id: uuid.UUID,
    payload: TaxRegimePeriodUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaxRegimePeriodOut:
    await _get_account_or_404(db, workspace_id, account_id)
    on = payload.effective_from or date.today()
    context = await resolve_tax_context(db, workspace_id, on)
    period = await tax_regime_service.update_regime_period(
        db, workspace_id, account_id, period_id, context.jurisdiction, payload.regime_code, payload.effective_from
    )
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="financial_account_tax_regime", entity_id=period.id,
    )
    await db.commit()
    return period


@router.delete("/accounts/{account_id}/regimes/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_regime(
    account_id: uuid.UUID,
    period_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_account_or_404(db, workspace_id, account_id)
    await tax_regime_service.delete_regime_period(db, workspace_id, account_id, period_id)
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="financial_account_tax_regime", entity_id=period_id,
    )
    await db.commit()


@router.get("/regimes/resolve", response_model=TaxRegimeResolveOut)
async def resolve_regime(
    account_id: uuid.UUID = Query(),
    on: date = Query(),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> TaxRegimeResolveOut:
    await _get_account_or_404(db, workspace_id, account_id)
    regime_code = await tax_regime_service.resolve_regime_at(db, workspace_id, account_id, on)
    return TaxRegimeResolveOut(regime_code=regime_code)


# --- Classificazione fiscale asset --------------------------------------------


@router.get("/asset-classifications", response_model=list[AssetTaxClassificationOut])
async def list_asset_classifications(
    on: date = Query(default_factory=date.today),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[AssetTaxClassificationOut]:
    context = await resolve_tax_context(db, workspace_id, on)
    views = await tax_classification_service.list_asset_classifications(db, workspace_id, context.jurisdiction, on)
    return [
        AssetTaxClassificationOut(
            asset_id=v.asset_id, asset_class=v.asset_class, is_override=v.is_override, codified=v.codified
        )
        for v in views
    ]


@router.put("/asset-classifications/{asset_id}", response_model=AssetTaxClassificationOut)
async def set_asset_classification(
    asset_id: uuid.UUID,
    payload: AssetTaxClassificationSetIn,
    on: date = Query(default_factory=date.today),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssetTaxClassificationOut:
    context = await resolve_tax_context(db, workspace_id, on)
    override = await tax_classification_service.set_asset_classification_override(
        db, workspace_id, context.jurisdiction, asset_id, payload.asset_class, on
    )
    codified_by_class = {c.code: c.codified for c in context.jurisdiction.tax_asset_classes(on)}
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="asset_tax_classification", entity_id=asset_id,
    )
    await db.commit()
    return AssetTaxClassificationOut(
        asset_id=asset_id,
        asset_class=override.asset_class,
        is_override=True,
        codified=codified_by_class.get(override.asset_class, False),
    )


@router.delete("/asset-classifications/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_classification(
    asset_id: uuid.UUID,
    on: date = Query(default_factory=date.today),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    context = await resolve_tax_context(db, workspace_id, on)
    await tax_classification_service.delete_asset_classification_override(
        db, workspace_id, context.jurisdiction, asset_id
    )
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="asset_tax_classification", entity_id=asset_id,
    )
    await db.commit()


# --- Saldi di apertura zainetto -----------------------------------------------


@router.get("/loss-pocket/openings", response_model=list[TaxLossOpeningOut])
async def list_loss_pocket_openings(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[TaxLossOpeningOut]:
    return await tax_opening_service.list_openings(db, workspace_id)


@router.post("/loss-pocket/openings", response_model=TaxLossOpeningOut, status_code=status.HTTP_201_CREATED)
async def create_loss_pocket_opening(
    payload: TaxLossOpeningCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaxLossOpeningOut:
    context = await resolve_tax_context(db, workspace_id, payload.formation_date)
    if payload.financial_account_id is not None:
        await _get_account_or_404(db, workspace_id, payload.financial_account_id)
    opening = await tax_opening_service.create_opening(
        db,
        workspace_id,
        context.jurisdiction,
        payload.financial_account_id,
        payload.formation_date,
        payload.income_category,
        payload.amount,
    )
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="tax_loss_opening_balance", entity_id=opening.id,
    )
    await db.commit()
    return opening


@router.patch("/loss-pocket/openings/{opening_id}", response_model=TaxLossOpeningOut)
async def update_loss_pocket_opening(
    opening_id: uuid.UUID,
    payload: TaxLossOpeningUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaxLossOpeningOut:
    on = payload.formation_date or date.today()
    context = await resolve_tax_context(db, workspace_id, on)
    opening = await tax_opening_service.update_opening(
        db, workspace_id, context.jurisdiction, opening_id,
        payload.formation_date, payload.income_category, payload.amount,
    )
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="tax_loss_opening_balance", entity_id=opening.id,
    )
    await db.commit()
    return opening


@router.delete("/loss-pocket/openings/{opening_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_loss_pocket_opening(
    opening_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await tax_opening_service.delete_opening(db, workspace_id, opening_id)
    await log_event(
        db, workspace_id, user.id, "TAX_SETTING_CHANGED",
        entity_type="tax_loss_opening_balance", entity_id=opening_id,
    )
    await db.commit()


# --- Zainetto ------------------------------------------------------------


@router.get("/loss-pocket", response_model=LossPocketOut)
async def get_loss_pocket(
    on: date = Query(),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> LossPocketOut:
    context = await resolve_tax_context(db, workspace_id, on)
    openings = await tax_opening_service.list_openings(db, workspace_id)
    entries = [
        LossPocketEntry(
            formation_date=o.formation_date,
            nominal=o.amount,
            income_category=o.income_category,
            perimeter=str(o.financial_account_id) if o.financial_account_id is not None else "dichiarativo",
            source="user_opening",
            formed_under_ruleset_code=o.formed_under_ruleset_code,
        )
        for o in openings
    ]
    ruleset = context.jurisdiction.ruleset_at(on)
    result = build_loss_pocket(entries, ruleset, on)
    return LossPocketOut(
        rows=[LossPocketRowOut(**vars(r)) for r in result.rows],
        totals_by_perimeter=result.totals_by_perimeter,
        residence_declared=context.residence_declared,
    )

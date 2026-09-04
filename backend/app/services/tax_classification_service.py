"""Override utente della classe fiscale di un asset + derivazione
(SPEC_TAX_REGIME.md FETTA 1). Una riga in `asset_tax_classifications` esiste
SOLO se l'utente sovrascrive il default derivato da
`TaxJurisdiction.derive_asset_class` — l'override vince sempre sul
derivato."""
import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.asset_tax_classification import AssetTaxClassification
from app.tax.base import AssetTaxRef, TaxJurisdiction


@dataclass(frozen=True)
class AssetClassificationView:
    asset_id: uuid.UUID
    asset_class: str | None
    is_override: bool
    codified: bool


def _asset_ref(asset: Asset) -> AssetTaxRef:
    return AssetTaxRef(asset_type=asset.asset_type, isin=asset.isin, name=asset.name)


async def _get_override(
    db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID, jurisdiction_code: str
) -> AssetTaxClassification | None:
    result = await db.execute(
        select(AssetTaxClassification).where(
            AssetTaxClassification.workspace_id == workspace_id,
            AssetTaxClassification.asset_id == asset_id,
            AssetTaxClassification.jurisdiction_code == jurisdiction_code,
        )
    )
    return result.scalar_one_or_none()


async def list_asset_classifications(
    db: AsyncSession, workspace_id: uuid.UUID, jurisdiction: TaxJurisdiction, on: date
) -> list[AssetClassificationView]:
    assets_result = await db.execute(select(Asset).where(Asset.workspace_id == workspace_id))
    assets = list(assets_result.scalars().all())

    overrides_result = await db.execute(
        select(AssetTaxClassification).where(
            AssetTaxClassification.workspace_id == workspace_id,
            AssetTaxClassification.jurisdiction_code == jurisdiction.code,
        )
    )
    overrides_by_asset = {o.asset_id: o for o in overrides_result.scalars().all()}
    codified_by_class = {c.code: c.codified for c in jurisdiction.tax_asset_classes(on)}

    views = []
    for asset in assets:
        override = overrides_by_asset.get(asset.id)
        asset_class = override.asset_class if override is not None else jurisdiction.derive_asset_class(
            _asset_ref(asset), on
        )
        views.append(
            AssetClassificationView(
                asset_id=asset.id,
                asset_class=asset_class,
                is_override=override is not None,
                codified=codified_by_class.get(asset_class, False) if asset_class is not None else False,
            )
        )
    return views


async def set_asset_classification_override(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    jurisdiction: TaxJurisdiction,
    asset_id: uuid.UUID,
    asset_class: str,
    on: date,
) -> AssetTaxClassification:
    valid_codes = {c.code for c in jurisdiction.tax_asset_classes(on)}
    if asset_class not in valid_codes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"asset_class {asset_class!r} sconosciuta")

    asset = await db.get(Asset, asset_id)
    if asset is None or asset.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset non trovato")

    override = await _get_override(db, workspace_id, asset_id, jurisdiction.code)
    if override is None:
        override = AssetTaxClassification(
            workspace_id=workspace_id,
            asset_id=asset_id,
            jurisdiction_code=jurisdiction.code,
            asset_class=asset_class,
        )
        db.add(override)
    else:
        override.asset_class = asset_class
    await db.flush()
    return override


async def delete_asset_classification_override(
    db: AsyncSession, workspace_id: uuid.UUID, jurisdiction: TaxJurisdiction, asset_id: uuid.UUID
) -> None:
    override = await _get_override(db, workspace_id, asset_id, jurisdiction.code)
    if override is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun override per questo asset")
    await db.delete(override)
    await db.flush()

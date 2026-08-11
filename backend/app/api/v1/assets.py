import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.schemas.assets import AssetCreate, AssetOut, AssetUpdate
from app.schemas.market_data import AssetPriceCreate, AssetPriceOut

router = APIRouter(prefix="/assets", tags=["portfolio"])


async def _get_asset_or_404(db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Asset:
    asset = Asset(workspace_id=workspace_id, **payload.model_dump())
    db.add(asset)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Symbol or ISIN already used in this workspace"
        ) from exc
    return asset


@router.get("", response_model=list[AssetOut])
async def list_assets(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    asset_type: str | None = None,
) -> list[Asset]:
    query = select(Asset).where(Asset.workspace_id == workspace_id)
    if asset_type is not None:
        query = query.where(Asset.asset_type == asset_type)
    result = await db.execute(query.order_by(Asset.name))
    return list(result.scalars().all())


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Asset:
    return await _get_asset_or_404(db, workspace_id, asset_id)


@router.patch("/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Asset:
    asset = await _get_asset_or_404(db, workspace_id, asset_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Symbol or ISIN already used in this workspace"
        ) from exc
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    asset = await _get_asset_or_404(db, workspace_id, asset_id)
    try:
        await db.delete(asset)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # RESTRICT da investment_transactions (SPEC §57: mai cancellare o
        # orfanizzare silenziosamente storico finanziario reale).
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Asset used by existing investment transactions, cannot be deleted",
        ) from exc


# --- Prezzi (SPEC §38 "dati manuali", sempre disponibili) ------------------


@router.get("/{asset_id}/prices", response_model=list[AssetPriceOut])
async def list_asset_prices(
    asset_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[AssetPrice]:
    await _get_asset_or_404(db, workspace_id, asset_id)
    result = await db.execute(
        select(AssetPrice)
        .where(AssetPrice.workspace_id == workspace_id, AssetPrice.asset_id == asset_id)
        .order_by(AssetPrice.price_date.desc())
        .limit(365)
    )
    return list(result.scalars().all())


@router.put("/{asset_id}/prices", response_model=AssetPriceOut)
async def upsert_manual_asset_price(
    asset_id: uuid.UUID,
    payload: AssetPriceCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AssetPrice:
    """Inserimento manuale di un prezzo (SPEC §38 "dati manuali") — SEMPRE
    disponibile, indipendentemente dal profilo `MarketDataProvider` attivo
    (vedi `ManualMarketDataProvider`): anche con un provider automatico
    configurato, l'utente puo' correggere un prezzo per un giorno specifico.
    Upsert su (asset, giorno): un secondo inserimento per lo stesso giorno
    sovrascrive, non duplica — stesso principio del refresh automatico
    (`app/worker/jobs/market_data.py`).
    """
    await _get_asset_or_404(db, workspace_id, asset_id)
    result = await db.execute(
        select(AssetPrice).where(
            AssetPrice.workspace_id == workspace_id,
            AssetPrice.asset_id == asset_id,
            AssetPrice.price_date == payload.price_date,
        )
    )
    price_row = result.scalar_one_or_none()
    if price_row is None:
        price_row = AssetPrice(
            workspace_id=workspace_id, asset_id=asset_id, price_date=payload.price_date
        )
        db.add(price_row)
    price_row.price = payload.price
    price_row.currency = payload.currency
    price_row.source = "manual"

    # flush+refresh PRIMA del commit (RLS ancora valida — SET LOCAL scade al
    # commit, vedi lumio-rls-gotchas): serve a normalizzare `price` alla
    # scala NUMERIC(18,6) della colonna, altrimenti la risposta esporrebbe
    # il Decimal Python non normalizzato invece del valore scritto da
    # Postgres (stesso bug gia' corretto in position_service.py).
    await db.flush()
    await db.refresh(price_row)
    await db.commit()
    return price_row

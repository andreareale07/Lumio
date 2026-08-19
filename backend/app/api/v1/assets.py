import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.db.session import get_db
from app.marketdata.base import AssetRef, MarketDataProviderError
from app.marketdata.registry import build_provider
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.asset_profile import AssetProfile
from app.schemas.assets import AssetCreate, AssetOut, AssetUpdate
from app.schemas.market_data import (
    AssetPriceCreate,
    AssetPriceOut,
    AssetProfileOut,
    PriceHistoryOut,
    PricePointOut,
)
from app.schemas.portfolio_analytics import AssetValuationOut
from app.services import analytics as analytics_service
from app.services import portfolio_analytics
from app.services.asset_profile_service import get_or_refresh_profile
from app.services.currency_service import currency_exists
from app.services.market_data_profile_service import get_active_profile

router = APIRouter(prefix="/assets", tags=["portfolio"])

# Preset -> persiste in asset_prices? (vedi piano Step 1: solo le barre
# giornaliere beneficiano anche la valorizzazione delle posizioni; gli
# intraday e i range molto ampi/a bassa granularita' restano "al volo", per
# non violare il vincolo di unicita' (workspace, asset, giorno) ne' sporcare
# la fonte usata da `compute_valuation` con un prezzo settimanale/mensile).
HISTORY_PRESETS: dict[str, bool] = {
    "1G": False,
    "1S": False,
    "1M": True,
    "3M": True,
    "6M": True,
    "1A": True,
    "5A": False,
    "Max": False,
}

# Ampiezza attesa di ciascun preset a persistenza giornaliera (vedi
# HISTORY_PRESETS sopra), usata SOLO per decidere se la cache locale basta a
# rispondere senza contattare Yahoo — endpoint non ufficiale, noto per
# rispondere 429/999 anche senza aver davvero superato un limite dichiarato
# (vedi yahoo.py). Un cambio di range nel grafico chiamava Yahoo ad ogni
# click: con l'utente che passa da un asset all'altro il volume di chiamate
# cresce in fretta e rischia il ban — la cache elimina la ripetizione entro
# la stessa finestra di dati gia' scaricata.
_PRESET_LOOKBACK_DAYS: dict[str, int] = {"1M": 31, "3M": 93, "6M": 186, "1A": 366}
# Copertura del bordo INIZIALE della finestra: mercati chiusi nel weekend/
# festivi vuol dire che la barra piu' vecchia disponibile e' spesso di
# qualche giorno dopo "since" per costruzione, mai un vero "buco" nei dati —
# senza questa tolleranza si richiederebbe un fetch live per ogni asset con
# uno storico piu' corto del lookback (es. appena importato).
_RANGE_COVERAGE_TOLERANCE_DAYS = 4
# Freschezza del bordo FINALE (il prezzo di OGGI, l'unico che puo' ancora
# cambiare — i giorni passati sono chiusi per sempre una volta finita la
# seduta): un TTL breve invece di un conteggio di giorni, cosi' la cache
# resta valida sia "tra un click e l'altro nella stessa sessione" sia "nel
# weekend, quando comunque non c'e' nulla di nuovo da scaricare" — nei due
# casi la richiesta successiva entro 15 minuti non deve mai ricontattare
# Yahoo.
_CACHE_TTL_MINUTES = 15


async def _cached_price_history(
    db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID, preset: str
) -> list[AssetPrice] | None:
    """Righe gia' in `asset_prices` che coprono per intero la finestra
    attesa dal preset E sono state aggiornate di recente, o `None` se manca
    l'una o l'altra condizione (mai una cache parziale: un grafico con un
    "buco" iniziale sarebbe piu' fuorviante di un fetch live)."""
    lookback_days = _PRESET_LOOKBACK_DAYS.get(preset)
    if lookback_days is None:
        return None
    since = date.today() - timedelta(days=lookback_days)
    rows = (
        await db.execute(
            select(AssetPrice)
            .where(
                AssetPrice.workspace_id == workspace_id,
                AssetPrice.asset_id == asset_id,
                AssetPrice.price_date >= since,
            )
            .order_by(AssetPrice.price_date)
        )
    ).scalars().all()
    if not rows:
        return None
    most_recent = max(rows, key=lambda r: r.updated_at)
    is_fresh = datetime.now(timezone.utc) - most_recent.updated_at <= timedelta(minutes=_CACHE_TTL_MINUTES)
    covers_range = (rows[0].price_date - since).days <= _RANGE_COVERAGE_TOLERANCE_DAYS
    return list(rows) if is_fresh and covers_range else None


async def _get_asset_or_404(db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


async def _get_display_name(db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID) -> str | None:
    result = await db.execute(
        select(AssetProfile.display_name).where(
            AssetProfile.workspace_id == workspace_id, AssetProfile.asset_id == asset_id
        )
    )
    return result.scalar_one_or_none()


def _to_asset_out(asset: Asset, display_name: str | None) -> AssetOut:
    return AssetOut(
        id=asset.id,
        workspace_id=asset.workspace_id,
        symbol=asset.symbol,
        isin=asset.isin,
        name=asset.name,
        asset_type=asset.asset_type,
        currency=asset.currency,
        notes=asset.notes,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        display_name=display_name,
    )


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AssetOut:
    if not await currency_exists(db, workspace_id, payload.currency):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown currency code")
    asset = Asset(workspace_id=workspace_id, **payload.model_dump())
    db.add(asset)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Symbol or ISIN already used in this workspace"
        ) from exc
    return _to_asset_out(asset, None)  # asset appena creato: nessuna cache di arricchimento ancora


@router.get("", response_model=list[AssetOut])
async def list_assets(
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
    asset_type: str | None = None,
) -> list[AssetOut]:
    # LEFT OUTER JOIN sulla cache gia' esistente (Step 3) — nessuna nuova
    # chiamata al provider da qui, solo lettura di cio' che e' gia' stato
    # scaricato aprendo il dettaglio di un asset in passato.
    query = (
        select(Asset, AssetProfile.display_name)
        .outerjoin(
            AssetProfile,
            (AssetProfile.asset_id == Asset.id) & (AssetProfile.workspace_id == Asset.workspace_id),
        )
        .where(Asset.workspace_id == workspace_id)
    )
    if asset_type is not None:
        query = query.where(Asset.asset_type == asset_type)
    rows = (await db.execute(query.order_by(Asset.name))).all()
    return [_to_asset_out(asset, display_name) for asset, display_name in rows]


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AssetOut:
    asset = await _get_asset_or_404(db, workspace_id, asset_id)
    display_name = await _get_display_name(db, workspace_id, asset_id)
    return _to_asset_out(asset, display_name)


@router.patch("/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: uuid.UUID,
    payload: AssetUpdate,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AssetOut:
    asset = await _get_asset_or_404(db, workspace_id, asset_id)
    updates = payload.model_dump(exclude_unset=True)
    if "currency" in updates and not await currency_exists(db, workspace_id, updates["currency"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown currency code")
    for field, value in updates.items():
        setattr(asset, field, value)
    # Letto PRIMA del commit (RLS gotcha noto: `SET LOCAL app.current_user_id`
    # scade al commit, una query successiva sulla stessa sessione perderebbe
    # l'identita' RLS — vedi la stessa correzione in app/api/v1/workspace.py).
    display_name = await _get_display_name(db, workspace_id, asset_id)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Symbol or ISIN already used in this workspace"
        ) from exc
    return _to_asset_out(asset, display_name)


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


@router.get("/{asset_id}/price-history", response_model=PriceHistoryOut)
async def get_asset_price_history(
    asset_id: uuid.UUID,
    preset: str,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> PriceHistoryOut:
    """Storico prezzi per il grafico di dettaglio asset. I preset
    giornalieri (`HISTORY_PRESETS`) vengono anche persistiti in
    `asset_prices` prima di rispondere — stesso beneficio della valorizzazione
    esistente (`compute_valuation` legge sempre da li'), un solo fetch serve
    entrambi gli scopi. `supports_history=False` quando il profilo attivo
    (es. manuale/stooq/custom) non implementa lo storico — mai un errore.
    """
    if preset not in HISTORY_PRESETS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid preset")
    asset = await _get_asset_or_404(db, workspace_id, asset_id)

    cached_rows = await _cached_price_history(db, workspace_id, asset_id, preset)
    if cached_rows is not None:
        return PriceHistoryOut(
            preset=preset,
            supports_history=True,
            currency=cached_rows[-1].currency,
            points=[
                PricePointOut(at=datetime.combine(r.price_date, time.min, tzinfo=timezone.utc), price=r.price)
                for r in cached_rows
            ],
        )

    profile = await get_active_profile(db, workspace_id)
    provider = build_provider(profile)
    asset_ref = AssetRef(
        id=asset.id, symbol=asset.symbol, isin=asset.isin, name=asset.name, currency=asset.currency
    )
    try:
        points = await provider.fetch_history(asset_ref, preset)
    except MarketDataProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if points is None:
        return PriceHistoryOut(
            preset=preset, supports_history=False, currency=asset.currency, points=[]
        )

    # `fetch_history` non porta una valuta (vedi PricePoint in base.py): il
    # simbolo Yahoo risolto da un ISIN puo' quotare in una valuta diversa da
    # `asset.currency` (es. un ISIN giapponese quotato in JPY anche se
    # l'asset e' registrato in EUR perche' comprato in EUR via Trade
    # Republic) — un bug reale ha sovrascritto prezzi corretti con
    # l'etichetta EUR, gonfiando il valore di mercato di ordini di
    # grandezza. `fetch_quote` la restituisce gia' (stesso simbolo risolto):
    # la si usa per tutti i punti di questo fetch, mai un secondo fetch per
    # punto (la valuta di un listino non cambia giorno per giorno).
    try:
        quote = await provider.fetch_quote(asset_ref)
    except MarketDataProviderError:
        quote = None
    price_currency = quote.currency if quote is not None else asset.currency

    if HISTORY_PRESETS[preset]:
        for point in points:
            price_date = point.at.date()
            result = await db.execute(
                select(AssetPrice).where(
                    AssetPrice.workspace_id == workspace_id,
                    AssetPrice.asset_id == asset_id,
                    AssetPrice.price_date == price_date,
                )
            )
            price_row = result.scalar_one_or_none()
            if price_row is None:
                price_row = AssetPrice(workspace_id=workspace_id, asset_id=asset_id, price_date=price_date)
                db.add(price_row)
            price_row.price = point.price
            price_row.currency = price_currency
            price_row.source = provider.provider
        await db.commit()

    return PriceHistoryOut(
        preset=preset,
        supports_history=True,
        currency=price_currency,
        points=[PricePointOut(at=p.at, price=p.price) for p in points],
    )


@router.get("/{asset_id}/valuation", response_model=AssetValuationOut)
async def get_asset_valuation(
    asset_id: uuid.UUID,
    currency: str | None = None,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AssetValuationOut:
    """Rendimento (costo/valore di mercato/P&L) convertito nella valuta
    richiesta (default: `base_currency` del workspace) — a differenza del
    calcolo client-side precedente, funziona anche quando il prezzo e' in
    una valuta diversa da quella della posizione (es. ISIN estero quotato
    in JPY/USD ma comprato in EUR): la card "Rendimento" del dettaglio
    asset non deve piu' sparire in quel caso, e' un dato che l'utente
    considera troppo importante per restare "—"."""
    await _get_asset_or_404(db, workspace_id, asset_id)
    resolved_currency = await analytics_service.resolve_currency(db, workspace_id, currency)
    valuation = await portfolio_analytics.get_asset_valuation(
        db, workspace_id, asset_id, date.today(), resolved_currency
    )
    return AssetValuationOut(
        currency=valuation.currency,
        quantity=valuation.quantity,
        cost_basis=valuation.cost_basis,
        market_value=valuation.market_value,
        unrealized_pl=valuation.unrealized_pl,
        realized_pl=valuation.realized_pl,
        has_market_data=valuation.has_market_data,
        has_missing_fx_rate=valuation.has_missing_fx_rate,
        price=valuation.price,
        price_native=valuation.price_native,
        price_native_currency=valuation.price_native_currency,
    )


@router.get("/{asset_id}/profile", response_model=AssetProfileOut)
async def get_asset_profile(
    asset_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AssetProfileOut:
    """Arricchimento best-effort (Step 3): emittente, categoria, AUM,
    accumulo/distribuzione. Cache di 30 giorni (`get_or_refresh_profile`) —
    nessun fetch a ogni apertura pagina. Sempre 200: un provider senza
    supporto o un fetch fallito rispondono con campi tutti `None`
    (`fetched_at=None` se non c'e' mai stata una cache), mai un errore.
    """
    asset = await _get_asset_or_404(db, workspace_id, asset_id)
    profile = await get_active_profile(db, workspace_id)
    provider = build_provider(profile)
    asset_ref = AssetRef(
        id=asset.id, symbol=asset.symbol, isin=asset.isin, name=asset.name, currency=asset.currency
    )
    cached = await get_or_refresh_profile(db, workspace_id, asset_id, asset_ref, provider)
    if cached is None:
        return AssetProfileOut(issuer=None, category=None, aum=None, distribution_policy=None, fetched_at=None)
    return AssetProfileOut.model_validate(cached)

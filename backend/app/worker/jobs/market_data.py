"""Job schedulato (cron giornaliero) + trigger manuale per l'aggiornamento
dei prezzi (SPEC §38). Per ogni workspace con un profilo `MarketDataProvider`
attivo diverso da "manual" (che non fa mai fetch, SPEC "dati manuali"),
scarica una quotazione per ogni asset con `symbol` impostato e la scrive in
`asset_prices` (upsert sul giorno della quotazione).

Un provider irraggiungibile o un singolo asset non risolvibile NON blocca
l'aggiornamento degli altri workspace/asset: si passa al successivo (stesso
principio del worker import, che non fa fallire l'intero batch per una riga
sola — qui la "riga" e' un asset).
"""
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.marketdata.base import AssetRef, MarketDataProviderError
from app.marketdata.registry import build_provider
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.services.market_data_profile_service import get_active_profile

logger = logging.getLogger(__name__)


async def list_workspace_owners() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Enumerazione via la funzione SECURITY DEFINER `list_workspace_owners()`
    (migration 0010): nessuna identita' RLS impostata su questa sessione,
    ma non serve — la funzione gira con i privilegi di `lumio_rls_helper`
    indipendentemente da chi la chiama (vedi il suo commento in migration)."""
    async with async_session_factory() as session:
        rows = (await session.execute(text("SELECT * FROM list_workspace_owners()"))).all()
    return [(row.workspace_id, row.owner_user_id) for row in rows]


async def _refresh_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    profile = await get_active_profile(db, workspace_id)
    if profile is None or profile.provider == "manual":
        return  # market data disabilitato o solo manuale: nulla da scaricare

    provider = build_provider(profile)
    assets = (
        await db.execute(
            select(Asset).where(Asset.workspace_id == workspace_id, Asset.symbol.is_not(None))
        )
    ).scalars().all()

    for asset in assets:
        try:
            quote = await provider.fetch_quote(
                AssetRef(id=asset.id, symbol=asset.symbol, isin=asset.isin, name=asset.name, currency=asset.currency)
            )
        except MarketDataProviderError as exc:
            logger.warning("market data non raggiungibile per asset %s: %s", asset.id, exc)
            continue
        if quote is None:
            continue

        result = await db.execute(
            select(AssetPrice).where(
                AssetPrice.workspace_id == workspace_id,
                AssetPrice.asset_id == asset.id,
                AssetPrice.price_date == quote.as_of,
            )
        )
        price_row = result.scalar_one_or_none()
        if price_row is None:
            price_row = AssetPrice(workspace_id=workspace_id, asset_id=asset.id, price_date=quote.as_of)
            db.add(price_row)
        price_row.price = quote.price
        price_row.currency = quote.currency
        price_row.source = profile.provider


async def refresh_market_data_job(ctx) -> None:
    for workspace_id, owner_user_id in await list_workspace_owners():
        async with rls_session(owner_user_id) as db:
            await _refresh_workspace(db, workspace_id)
            await db.commit()


async def refresh_market_data_for_workspace(ctx, workspace_id: str, user_id: str) -> None:
    """Job arq per il trigger manuale (`POST /market-data/refresh`, vedi
    `app/worker/queue.py`) — UN solo workspace, stessa logica del cron ma
    senza attendere il refresh di tutti gli altri. `user_id` e' chi ha
    premuto il pulsante (gia' verificato membro del workspace dalla
    dependency `get_current_workspace_id`): a differenza del cron, che non
    ha una richiesta HTTP da cui ricavare un'identita' e usa sempre il
    proprietario, qui non serve risalire all'owner."""
    async with rls_session(uuid.UUID(user_id)) as db:
        await _refresh_workspace(db, uuid.UUID(workspace_id))
        await db.commit()

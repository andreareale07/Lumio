"""Job schedulato (cron giornaliero) + trigger manuale per l'aggiornamento
dei prezzi (SPEC §38). Per ogni workspace con un profilo `MarketDataProvider`
attivo diverso da "manual" (che non fa mai fetch, SPEC "dati manuali"),
scarica una quotazione per ogni asset con `symbol` o `isin` impostato e la
scrive in `asset_prices` (upsert sul giorno della quotazione) — la
risoluzione ISIN→ticker, quando serve, e' responsabilita' del singolo
provider (es. `YahooProvider._resolve_symbol_from_isin`), non di questo job.

Un provider irraggiungibile o un singolo asset non risolvibile NON blocca
l'aggiornamento degli altri workspace/asset: si passa al successivo (stesso
principio del worker import, che non fa fallire l'intero batch per una riga
sola — qui la "riga" e' un asset).
"""
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.marketdata.base import AssetRef, MarketDataProviderError
from app.marketdata.registry import build_provider
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.services.job_run_tracker import tracked_job_run
from app.services.market_data_profile_service import get_active_profile

logger = logging.getLogger(__name__)

JOB_KIND = "market_data_refresh"


@dataclass
class RefreshSummary:
    checked: int
    updated: int


def _refresh_message(summary: RefreshSummary) -> str:
    if summary.checked == 0:
        return "Nessun asset da aggiornare (nessun provider attivo o nessun asset con simbolo/ISIN)."
    return f"{summary.updated} prezzi aggiornati su {summary.checked} asset."


async def list_workspace_owners() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Enumerazione via la funzione SECURITY DEFINER `list_workspace_owners()`
    (migration 0010): nessuna identita' RLS impostata su questa sessione,
    ma non serve — la funzione gira con i privilegi di `lumio_rls_helper`
    indipendentemente da chi la chiama (vedi il suo commento in migration)."""
    async with async_session_factory() as session:
        rows = (await session.execute(text("SELECT * FROM list_workspace_owners()"))).all()
    return [(row.workspace_id, row.owner_user_id) for row in rows]


async def _refresh_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> RefreshSummary:
    profile = await get_active_profile(db, workspace_id)
    if profile is None or profile.provider == "manual":
        return RefreshSummary(checked=0, updated=0)  # market data disabilitato o solo manuale: nulla da scaricare

    provider = build_provider(profile)
    assets = (
        await db.execute(
            select(Asset).where(
                Asset.workspace_id == workspace_id,
                or_(Asset.symbol.is_not(None), Asset.isin.is_not(None)),
            )
        )
    ).scalars().all()

    updated = 0
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
        updated += 1

    return RefreshSummary(checked=len(assets), updated=updated)


async def refresh_market_data_job(ctx) -> None:
    for workspace_id, owner_user_id in await list_workspace_owners():
        try:
            async with tracked_job_run(workspace_id, owner_user_id, JOB_KIND) as run:
                async with rls_session(owner_user_id) as db:
                    summary = await _refresh_workspace(db, workspace_id)
                    await db.commit()
                run.message = _refresh_message(summary)
        except Exception:
            # Un workspace fallito non deve bloccare il refresh degli altri
            # (stesso principio gia' applicato per asset singolo dentro
            # _refresh_workspace) — lo stato "failed" e' comunque scritto da
            # tracked_job_run prima di ri-lanciare, qui lo si logga e basta.
            logger.exception("refresh prezzi cron falito per workspace %s", workspace_id)


async def refresh_market_data_for_workspace(ctx, workspace_id: str, user_id: str) -> None:
    """Job arq per il trigger manuale (`POST /market-data/refresh`, vedi
    `app/worker/queue.py`) — UN solo workspace, stessa logica del cron ma
    senza attendere il refresh di tutti gli altri. `user_id` e' chi ha
    premuto il pulsante (gia' verificato membro del workspace dalla
    dependency `get_current_workspace_id`): a differenza del cron, che non
    ha una richiesta HTTP da cui ricavare un'identita' e usa sempre il
    proprietario, qui non serve risalire all'owner."""
    ws_id, uid = uuid.UUID(workspace_id), uuid.UUID(user_id)
    async with tracked_job_run(ws_id, uid, JOB_KIND) as run:
        async with rls_session(uid) as db:
            summary = await _refresh_workspace(db, ws_id)
            await db.commit()
        run.message = _refresh_message(summary)

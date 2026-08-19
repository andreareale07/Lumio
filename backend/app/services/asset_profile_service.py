"""Cache dell'arricchimento asset (Step 3 pagina dettaglio) — ponte tra
l'API e `MarketDataProvider.fetch_profile`. I dati di un fondo (emittente,
categoria, AUM) cambiano di rado: si rifa' un fetch solo se la cache e'
assente o piu' vecchia di `_CACHE_TTL`, mai a ogni apertura pagina (SPEC
Step 3).
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketdata.base import AssetRef, MarketDataProvider
from app.models.asset_profile import AssetProfile

_CACHE_TTL = timedelta(days=30)


async def get_or_refresh_profile(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    asset_ref: AssetRef,
    provider: MarketDataProvider,
) -> AssetProfile | None:
    result = await db.execute(
        select(AssetProfile).where(AssetProfile.workspace_id == workspace_id, AssetProfile.asset_id == asset_id)
    )
    cached = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    # Una cache senza `display_name` non e' mai considerata fresca, a
    # prescindere dal TTL: quasi ogni titolo quotato ha un nome su Yahoo, un
    # `None` qui e' quasi sempre un fetch riuscito ma incompleto (endpoint
    # noto per essere fragile, vedi fetch_profile) — bloccarlo per 30 giorni
    # come un dato "confermato assente" negherebbe per un mese un nome che
    # un secondo tentativo troverebbe subito (bug reale osservato: D-Wave).
    is_fresh = cached is not None and now - cached.fetched_at < _CACHE_TTL and cached.display_name is not None
    if is_fresh:
        return cached

    fetched = await provider.fetch_profile(asset_ref)
    if fetched is None:
        # Fetch fallito o provider senza supporto: una cache scaduta ma
        # presente resta comunque piu' utile di niente (i dati di fondo
        # cambiano di rado) — non la si cancella per un singolo fetch fallito.
        return cached

    if cached is None:
        cached = AssetProfile(workspace_id=workspace_id, asset_id=asset_id)
        db.add(cached)
    # Merge campo per campo: un fetch che non trova un campo (es. un
    # `display_name` mancante per un problema transitorio) non deve
    # cancellare un valore gia' noto e buono da un fetch precedente — ogni
    # campo di AssetProfile e' indipendentemente opzionale (vedi il suo
    # docstring), la cache deve rispettare la stessa garanzia.
    if fetched.issuer is not None:
        cached.issuer = fetched.issuer
    if fetched.category is not None:
        cached.category = fetched.category
    if fetched.aum is not None:
        cached.aum = fetched.aum
    if fetched.distribution_policy is not None:
        cached.distribution_policy = fetched.distribution_policy
    if fetched.display_name is not None:
        cached.display_name = fetched.display_name
    cached.fetched_at = now

    await db.flush()
    await db.refresh(cached)
    await db.commit()
    return cached

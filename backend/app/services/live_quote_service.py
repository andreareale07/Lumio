"""Live-quote per il dettaglio di un singolo asset (docs/SPEC_STOCK_PRICE.md).

Tre livelli distinti, per non ripetere l'errore che la SPEC vuole evitare
esplicitamente ("il prezzo daily non deve diventare l'ultimo prezzo visto
perche' qualcuno ha aperto la pagina"):

- `asset_prices` (daily canonico, INVARIATA) — mai toccata da questo modulo.
- `asset_price_quotes` (intraday osservato) — una riga per ogni fetch reale
  riuscito, mai un upsert su un valore corrente.
- Redis `market:quote:{workspace}:{asset}` — cache pura, TTL, sacrificabile:
  un riavvio di Redis non perde nulla di storico, si ri-scalda al prossimo
  miss.

Anti cache-stampede: un lock `market:quote:lock:{...}` (SET NX + TTL breve)
garantisce che, quando la cache scade, un solo fetch reale al provider parta
per finestra di refresh — le richieste concorrenti aspettano un budget breve
e poi riusano il valore appena scritto dal vincitore del lock, o ricadono
sull'ultimo dato noto (mai un secondo fetch in parallelo, mai un blocco a
oltranza).
"""
import asyncio
import json
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.marketdata.base import AssetRef, MarketDataProviderError
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.asset_price_quote import AssetPriceQuote
from app.models.market_data_profile import MarketDataProfile

logger = logging.getLogger(__name__)

# Budget d'attesa per chi NON vince il lock: abbastanza per coprire il
# round-trip tipico di un fetch Yahoo (vedi _TIMEOUT in providers/yahoo.py),
# mai a oltranza — oltre questo si ricade sull'ultimo dato noto (Caso 3).
_LOCK_TTL_SECONDS = 10
_LOCK_WAIT_ATTEMPTS = 5
_LOCK_WAIT_INTERVAL_SECONDS = 0.2


@dataclass(frozen=True)
class LiveQuote:
    price: Decimal
    currency: str
    quoted_at: datetime
    # True quando questo NON e' un fetch fresco (provider irraggiungibile,
    # lock non vinto e nessun aggiornamento apparso entro il budget d'attesa)
    # ma l'ultimo dato noto (intraday o daily) mostrato per onestà invece di
    # un errore — la UI puo' segnalarlo (es. "aggiornato alle HH:MM").
    stale: bool


def _quote_key(workspace_id: uuid.UUID, asset_id: uuid.UUID) -> str:
    return f"market:quote:{workspace_id}:{asset_id}"


def _lock_key(workspace_id: uuid.UUID, asset_id: uuid.UUID) -> str:
    return f"market:quote:lock:{workspace_id}:{asset_id}"


def _encode(price: Decimal, currency: str, quoted_at: datetime) -> str:
    return json.dumps({"price": str(price), "currency": currency, "quoted_at": quoted_at.isoformat()})


def _decode(raw: bytes) -> LiveQuote:
    payload = json.loads(raw.decode())
    return LiveQuote(
        price=Decimal(payload["price"]),
        currency=payload["currency"],
        quoted_at=datetime.fromisoformat(payload["quoted_at"]),
        stale=False,
    )


async def _get_cached(workspace_id: uuid.UUID, asset_id: uuid.UUID) -> LiveQuote | None:
    raw = await redis_client.get(_quote_key(workspace_id, asset_id))
    return _decode(raw) if raw is not None else None


async def _set_cached(
    workspace_id: uuid.UUID, asset_id: uuid.UUID, price: Decimal, currency: str, quoted_at: datetime, ttl_seconds: int
) -> None:
    # Caso 4 (SPEC): mai sovrascrivere un valore gia' in cache con uno piu'
    # vecchio — rilevante solo in teoria qui (il fetch appena avvenuto e'
    # sempre il piu' recente in pratica), ma la guardia costa poco ed evita
    # sorprese se in futuro piu' fonti scrivessero la stessa chiave.
    existing = await _get_cached(workspace_id, asset_id)
    if existing is not None and existing.quoted_at >= quoted_at:
        return
    await redis_client.set(
        _quote_key(workspace_id, asset_id), _encode(price, currency, quoted_at), ex=ttl_seconds
    )


async def _persist_observation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    price: Decimal,
    currency: str,
    quoted_at: datetime,
    source: str,
) -> None:
    stmt = (
        pg_insert(AssetPriceQuote)
        .values(
            workspace_id=workspace_id,
            asset_id=asset_id,
            quoted_at=quoted_at,
            price=price,
            currency=currency,
            source=source,
        )
        .on_conflict_do_nothing(index_elements=["workspace_id", "asset_id", "quoted_at"])
    )
    await db.execute(stmt)


async def persist_intraday_points(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    points: list[tuple[datetime, Decimal]],
    currency: str,
    source: str,
) -> None:
    """Semina `asset_price_quotes` con punti gia' scaricati altrove (fallback
    del grafico "1G"/"1S" in `app/api/v1/assets.py` quando la nostra cache
    intraday e' insufficiente) — cosi' le richieste successive nello stesso
    giorno smettono di ricontattare il provider per lo stesso range. Un solo
    commit per l'intero batch (a differenza di `get_or_refresh_latest_quote`,
    che ne fa uno per singola quotazione)."""
    for quoted_at, price in points:
        await _persist_observation(db, workspace_id, asset_id, price, currency, quoted_at, source)
    await db.commit()


async def _fallback_quote(db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID) -> LiveQuote | None:
    """Ultimo dato noto (Caso 3: provider down, MAI un errore che rompe la
    pagina, MAI una cancellazione dello storico): prima l'osservazione
    intraday piu' recente (piu' granulare), altrimenti il prezzo daily
    canonico. `None` solo se non esiste letteralmente nessun dato."""
    intraday = (
        await db.execute(
            select(AssetPriceQuote)
            .where(AssetPriceQuote.workspace_id == workspace_id, AssetPriceQuote.asset_id == asset_id)
            .order_by(AssetPriceQuote.quoted_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if intraday is not None:
        return LiveQuote(price=intraday.price, currency=intraday.currency, quoted_at=intraday.quoted_at, stale=True)

    daily = (
        await db.execute(
            select(AssetPrice)
            .where(AssetPrice.workspace_id == workspace_id, AssetPrice.asset_id == asset_id)
            .order_by(AssetPrice.price_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if daily is None:
        return None
    return LiveQuote(
        price=daily.price,
        currency=daily.currency,
        quoted_at=datetime.combine(daily.price_date, datetime.min.time(), tzinfo=timezone.utc),
        stale=True,
    )


async def get_or_refresh_latest_quote(
    db: AsyncSession, workspace_id: uuid.UUID, asset: Asset, profile: MarketDataProfile | None
) -> LiveQuote | None:
    """Quotazione "live" per il dettaglio di UN asset. MAI scrive
    `asset_prices`: solo Redis + l'osservazione intraday `asset_price_quotes`
    (regola esplicita SPEC: la visita di una pagina non deve modificare
    retroattivamente il prezzo daily canonico). `None` = nessun profilo
    attivo o profilo "manual" (che non fa mai fetch) — il chiamante ricade
    sul solo prezzo daily come faceva prima di questa feature."""
    if profile is None or profile.provider == "manual":
        return None

    cached = await _get_cached(workspace_id, asset.id)
    if cached is not None:
        return cached

    lock_key = _lock_key(workspace_id, asset.id)
    acquired = await redis_client.set(lock_key, secrets.token_hex(8), nx=True, ex=_LOCK_TTL_SECONDS)

    if not acquired:
        # Caso 1/2 (SPEC): qualcun altro sta gia' facendo il fetch reale per
        # questo stesso asset — si aspetta un budget breve che scriva lui il
        # valore, mai un secondo fetch in parallelo.
        for _ in range(_LOCK_WAIT_ATTEMPTS):
            await asyncio.sleep(_LOCK_WAIT_INTERVAL_SECONDS)
            cached = await _get_cached(workspace_id, asset.id)
            if cached is not None:
                return cached
        return await _fallback_quote(db, workspace_id, asset.id)

    # Import locale: evita un ciclo (registry importa modelli/provider, non
    # questo servizio) e mantiene il provider ignaro di Redis/lock/intraday.
    from app.marketdata.registry import build_provider

    provider = build_provider(profile)
    asset_ref = AssetRef(
        id=asset.id, symbol=asset.symbol, isin=asset.isin, name=asset.name, currency=asset.currency
    )
    try:
        quote = await provider.fetch_quote(asset_ref)
    except MarketDataProviderError as exc:
        logger.warning("live-quote non raggiungibile per asset %s: %s", asset.id, exc)
        return await _fallback_quote(db, workspace_id, asset.id)

    if quote is None:
        return await _fallback_quote(db, workspace_id, asset.id)

    # `Quote.as_of` e' una `date` (vedi app/marketdata/base.py): il provider
    # "chart" di Yahoo non espone un istante intraday utilizzabile in modo
    # uniforme tra tutti i provider. Si usa il momento del fetch stesso come
    # `quoted_at` — coerente con la decisione di non toccare il Protocol
    # provider (nessun refactor non necessario, vedi piano) e accurato a
    # questa scala (il fetch avviene sincronamente quando serve, nessun
    # ritardo significativo tra risposta del provider e "adesso").
    quoted_at = datetime.now(timezone.utc)

    await _set_cached(
        workspace_id, asset.id, quote.price, quote.currency, quoted_at, profile.detail_refresh_interval_seconds + 5
    )
    # NESSUN commit qui (stesso RLS gotcha di _cleanup_intraday_quotes in
    # worker/jobs/market_data.py: `SET LOCAL app.current_user_id` scade al
    # commit). Questa funzione gira dentro una richiesta HTTP
    # (`GET /assets/{id}/valuation`) che dopo di qui esegue ANCORA query
    # RLS-dipendenti (`portfolio_analytics.get_asset_valuation` legge
    # `Position`) sulla STESSA sessione — un commit intermedio le romperebbe
    # (bug reale osservato in QA manuale: la seconda richiesta concorrente
    # falliva con "invalid input syntax for type uuid: ''"). Il commit
    # dell'INSERT in asset_price_quotes resta a carico del chiamante
    # (`assets.py::get_asset_valuation`), UNA sola volta a fine handler.
    await _persist_observation(db, workspace_id, asset.id, quote.price, quote.currency, quoted_at, profile.provider)

    return LiveQuote(price=quote.price, currency=quote.currency, quoted_at=quoted_at, stale=False)

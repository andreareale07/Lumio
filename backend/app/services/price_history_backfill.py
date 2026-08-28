"""Fase 'prezzi storici' del backfill patrimonio (FETTA 3, storico
patrimonio ricostruito) — scarica lo storico dei prezzi per gli asset
DAVVERO posseduti + lo storico FX all'indietro, cosi' che
`compute_historical_series` (chiamata dal backfill con un checkpoint per
OGNI giorno, vedi `portfolio_analytics.compute_net_worth_backfill_series`)
possa valorizzare a prezzo di mercato anche i giorni passati, non solo
quello odierno gia' coperto da `worker/jobs/market_data.py`.

Modellato su `market_data.py::_refresh_workspace`/`_backfill_fx_history`
(refresh quotidiano) ma con differenze deliberate:
- range ESPLICITO per asset (`[prima_operazione, oggi]`), mai un preset
  fisso: un ETF comprato il mese scorso non deve innescare un download
  decennale.
- MAI far fallire l'intera fase per un provider assente/in errore — un
  errore su un asset passa al successivo (contatore in
  `PriceBackfillSummary`, mai un'eccezione propagata), e dopo troppi errori
  CONSECUTIVI la fase si ferma (gli asset restanti restano a costo storico,
  mai un crash del job — DoD M09).
- rate limiting esplicito fra una chiamata e la successiva
  (`market_data_backfill_delay_seconds`): il refresh quotidiano fa UNA
  chiamata per asset, qui se ne fanno potenzialmente decine in sequenza in
  un colpo solo.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.marketdata.base import AssetRef, MarketDataProviderError, PricePoint
from app.marketdata.registry import build_provider
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.financial_account import FinancialAccount
from app.models.fx_rate import FxRate
from app.models.investment_transaction import InvestmentTransaction
from app.services import fx_rate_service
from app.services.market_data_profile_service import get_active_profile

logger = logging.getLogger(__name__)

# Stesso pattern/nome di intento di
# `ai_classification_job.MAX_CONSECUTIVE_PROVIDER_ERRORS`: un provider
# irraggiungibile per N asset di fila non deve far scorrere l'intera fase
# fingendo un tentativo per ogni asset rimanente — si interrompe SOLO questa
# fase (mai il job intero, gli asset restanti restano a costo storico).
MAX_CONSECUTIVE_PROVIDER_ERRORS = 5
# Mercati chiusi nei weekend/festivi: la riga piu' vecchia gia' salvata puo'
# essere di qualche giorno dopo la prima operazione senza che manchi
# davvero copertura.
_COVERAGE_SLACK_DAYS = 7


@dataclass
class _AssetBackfillTarget:
    asset: Asset
    first_trade_date: date


@dataclass
class PriceBackfillSummary:
    assets_checked: int = 0
    assets_updated: int = 0
    assets_skipped_covered: int = 0
    assets_errors: int = 0
    fx_pairs_updated: int = 0


async def _owned_assets(db: AsyncSession, workspace_id: uuid.UUID) -> list[_AssetBackfillTarget]:
    """Solo gli asset DAVVERO posseduti (con almeno un movimento in
    `investment_transactions`) e risolvibili da un provider (symbol o isin)
    — un asset "Other" senza nessuno dei due non e' mai risolvibile (vedi
    `Asset` docstring), niente da scaricare per lui."""
    rows = (
        await db.execute(
            select(InvestmentTransaction.asset_id, func.min(InvestmentTransaction.trade_date))
            .where(
                InvestmentTransaction.workspace_id == workspace_id,
                InvestmentTransaction.asset_id.is_not(None),
            )
            .group_by(InvestmentTransaction.asset_id)
        )
    ).all()
    if not rows:
        return []
    first_trade_by_asset = {asset_id: first_date for asset_id, first_date in rows}

    assets = (
        await db.execute(
            select(Asset).where(
                Asset.workspace_id == workspace_id,
                Asset.id.in_(first_trade_by_asset.keys()),
                or_(Asset.symbol.is_not(None), Asset.isin.is_not(None)),
            )
        )
    ).scalars().all()
    return [
        _AssetBackfillTarget(asset=asset, first_trade_date=first_trade_by_asset[asset.id]) for asset in assets
    ]


async def _is_covered(db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID, first_trade_date: date) -> bool:
    """Copertura minima oltre la quale non ha senso richiedere di nuovo
    l'intero storico: se la riga piu' vecchia gia' salvata risale a non piu'
    di `_COVERAGE_SLACK_DAYS` dopo la prima operazione, l'asset e' gia'
    coperto. Piu' preciso del `_FX_HISTORY_COVERAGE_DAYS = 730` fisso usato
    dal refresh quotidiano — sicuro qui perche' QUESTO job non e' sul cron
    (nessun rischio di richiedere 'Max' ogni notte)."""
    earliest = (
        await db.execute(
            select(func.min(AssetPrice.price_date)).where(
                AssetPrice.workspace_id == workspace_id, AssetPrice.asset_id == asset_id
            )
        )
    ).scalar_one_or_none()
    if earliest is None:
        return False
    return earliest <= first_trade_date + timedelta(days=_COVERAGE_SLACK_DAYS)


async def _persist_price_points(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    points: list[PricePoint],
    currency: str,
    source: str,
) -> None:
    if not points:
        return
    # Un punto per giorno: se lo stesso giorno compare piu' volte nella
    # risposta (non atteso, ma difensivo) l'ultimo vince — stesso principio
    # di "upsert, non accumulo" del resto del modulo asset_prices.
    deduped: dict[date, dict] = {}
    for point in points:
        deduped[point.at.date()] = {
            "workspace_id": workspace_id,
            "asset_id": asset_id,
            "price_date": point.at.date(),
            "price": point.price,
            "currency": currency,
            "source": source,
        }
    stmt = pg_insert(AssetPrice).values(list(deduped.values()))
    stmt = stmt.on_conflict_do_update(
        constraint="uq_asset_prices_asset_date",
        set_={"price": stmt.excluded.price, "currency": stmt.excluded.currency, "source": stmt.excluded.source},
    )
    await db.execute(stmt)


async def list_price_backfill_targets(
    db: AsyncSession, workspace_id: uuid.UUID
) -> list[_AssetBackfillTarget]:
    """Elenco degli asset da scaricare (posseduti, risolvibili, non ancora
    coperti) — letto in UNA sessione di sola lettura ('sessione A' del job,
    vedi `worker/jobs/snapshot_backfill.py`). La fase di fetch/scrittura vera
    (`backfill_one_asset_price`) apre poi una sessione RLS FRESCA per ogni
    singolo asset: le chiamate HTTP durano secondi (rate limiting incluso),
    mai tenerle dentro una transazione DB aperta a lungo — stessa regola
    "SET LOCAL scade al commit" di `job_run_tracker.py`."""
    targets = await _owned_assets(db, workspace_id)
    result = []
    for target in targets:
        if not await _is_covered(db, workspace_id, target.asset.id, target.first_trade_date):
            result.append(target)
    return result


async def backfill_one_asset_price(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    provider,
    provider_name: str,
    target: _AssetBackfillTarget,
    date_to: date,
) -> bool:
    """Scarica e persiste lo storico `[prima_operazione, date_to]` per UN
    solo asset — il chiamante apre la sessione, commit e chiude (stesso
    principio di ogni altra scrittura di questo modulo, mai un commit
    implicito qui). Ritorna `True` se almeno un punto e' stato scritto.
    Solleva `MarketDataProviderError` se la chiamata al provider fallisce
    (il chiamante conta gli errori consecutivi e decide se interrompere la
    fase — vedi `MAX_CONSECUTIVE_PROVIDER_ERRORS`)."""
    asset_ref = AssetRef(
        id=target.asset.id,
        symbol=target.asset.symbol,
        isin=target.asset.isin,
        name=target.asset.name,
        currency=target.asset.currency,
    )
    points = await provider.fetch_history_range(asset_ref, target.first_trade_date, date_to)
    if points is None:
        # Provider senza supporto per un range arbitrario (§3.5): meglio un
        # preset limitato che niente.
        points = await provider.fetch_history(asset_ref, "1A")
    if not points:
        return False

    # Valuta EFFETTIVA del listino risolto, mai `asset.currency` da solo (un
    # ISIN puo' risolvere a un simbolo quotato in una valuta diversa — bug
    # reale gia' documentato in `assets.py`/`get_asset_price_history` che ha
    # gonfiato valori di mercato di ordini di grandezza).
    try:
        quote = await provider.fetch_quote(asset_ref)
    except MarketDataProviderError:
        quote = None
    price_currency = quote.currency if quote is not None else target.asset.currency

    await _persist_price_points(db, workspace_id, target.asset.id, points, price_currency, provider_name)
    return True


async def backfill_fx_history(db: AsyncSession, workspace_id: uuid.UUID, base_currency: str, date_from: date) -> int:
    """FX all'indietro (§3.5): per ogni valuta EFFETTIVAMENTE in uso nel
    workspace (asset/conti/quotazioni gia' scaricate — stessa query a tre
    fonti di `market_data.py::_refresh_fx_rates`), scarica
    `[date_from, tasso_piu_vecchio_gia_esistente[. Simmetrico a
    `_backfill_fx_history` del refresh quotidiano (che va SOLO in avanti dal
    preset 'Max', mensile su Yahoo e comunque insufficiente per un backfill
    di anni)."""
    profile = await get_active_profile(db, workspace_id)
    if profile is None or profile.provider == "manual":
        return 0
    provider = build_provider(profile)
    delay = get_settings().market_data_backfill_delay_seconds

    asset_currencies = (
        await db.execute(select(Asset.currency).where(Asset.workspace_id == workspace_id).distinct())
    ).scalars().all()
    account_currencies = (
        await db.execute(
            select(FinancialAccount.currency).where(FinancialAccount.workspace_id == workspace_id).distinct()
        )
    ).scalars().all()
    price_currencies = (
        await db.execute(select(AssetPrice.currency).where(AssetPrice.workspace_id == workspace_id).distinct())
    ).scalars().all()
    foreign_currencies = {
        c for c in (*asset_currencies, *account_currencies, *price_currencies) if c != base_currency
    }

    updated = 0
    for currency in foreign_currencies:
        earliest = (
            await db.execute(
                select(func.min(FxRate.rate_date)).where(
                    FxRate.from_currency == currency, FxRate.to_currency == base_currency
                )
            )
        ).scalar_one_or_none()
        if earliest is not None and earliest <= date_from:
            continue  # gia' copre l'intero range richiesto, nulla da scaricare
        range_to = (earliest - timedelta(days=1)) if earliest is not None else date.today()
        if date_from > range_to:
            continue

        try:
            points = await provider.fetch_fx_history_range(currency, base_currency, date_from, range_to)
        except MarketDataProviderError as exc:
            logger.warning("backfill FX non riuscito per %s->%s: %s", currency, base_currency, exc)
            continue
        if not points:
            await asyncio.sleep(delay)
            continue
        for point in points:
            await fx_rate_service.upsert_rate(
                db, currency, base_currency, point.at.date(), point.price, profile.provider
            )
        updated += len(points)
        await asyncio.sleep(delay)

    return updated

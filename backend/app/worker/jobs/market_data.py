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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory
from app.db.rls import rls_session
from app.marketdata.base import AssetRef, MarketDataProviderError
from app.marketdata.registry import build_provider
from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.asset_price_quote import AssetPriceQuote
from app.models.financial_account import FinancialAccount
from app.models.fx_rate import FxRate
from app.models.position import Position
from app.models.workspace import Workspace
from app.services import fx_rate_service
from app.services.job_run_tracker import tracked_job_run
from app.services.market_data_profile_service import get_active_profile
from app.services.system_settings_service import is_job_enabled

# docs/SPEC_STOCK_PRICE.md: le osservazioni intraday servono solo ad
# arricchire il grafico "1G"/"1S" del giorno corrente (vedi
# app/api/v1/assets.py) — non uno storico a lungo termine, quindi una
# retention breve basta ed evita una tabella che cresce senza limite.
_INTRADAY_QUOTE_RETENTION_DAYS = 3

logger = logging.getLogger(__name__)

JOB_KIND = "market_data_refresh"


@dataclass
class RefreshSummary:
    checked: int
    updated: int
    fx_updated: int = 0


def _refresh_message(summary: RefreshSummary) -> str:
    if summary.checked == 0 and summary.fx_updated == 0:
        return "Nessun asset da aggiornare (nessun provider attivo o nessun asset con simbolo/ISIN)."
    message = f"{summary.updated} prezzi aggiornati su {summary.checked} asset."
    if summary.fx_updated:
        message += f" {summary.fx_updated} tassi di cambio aggiornati."
    return message


async def _refresh_fx_rates(
    db: AsyncSession, workspace_id: uuid.UUID, provider, base_currency: str, source: str
) -> int:
    """Aggiorna `fx_rates` per le valute EFFETTIVAMENTE in uso nel workspace
    verso la `base_currency` — mai tutte le combinazioni possibili, stesso
    principio "un solo asset per volta" gia' usato per i prezzi qui sopra.
    Stesso profilo attivo dell'asset market data, nessun concetto di
    "provider FX" separato (SPEC sistema di valute).

    "In uso" include sia la valuta DICHIARATA di asset/conti sia quella
    EFFETTIVA delle quotazioni gia' scaricate (`AssetPrice.currency`): un
    asset puo' essere registrato in EUR (come l'ha comprato l'utente) ma
    quotato da Yahoo in una valuta diversa (es. un ISIN giapponese in JPY)
    — senza questa seconda fonte quella valuta non verrebbe mai riconosciuta
    come "in uso" e il tasso di cambio necessario a convertirla non
    verrebbe mai scaricato, lasciando la posizione bloccata sul fallback a
    costo storico anche a bug di etichettatura gia' corretto."""
    asset_currencies = (
        await db.execute(select(Asset.currency).where(Asset.workspace_id == workspace_id).distinct())
    ).scalars().all()
    account_currencies = (
        await db.execute(
            select(FinancialAccount.currency).where(FinancialAccount.workspace_id == workspace_id).distinct()
        )
    ).scalars().all()
    price_currencies = (
        await db.execute(
            select(AssetPrice.currency).where(AssetPrice.workspace_id == workspace_id).distinct()
        )
    ).scalars().all()
    foreign_currencies = {
        c for c in (*asset_currencies, *account_currencies, *price_currencies) if c != base_currency
    }

    updated = 0
    for currency in foreign_currencies:
        try:
            quote = await provider.fetch_fx_rate(currency, base_currency)
        except MarketDataProviderError as exc:
            logger.warning("tasso di cambio non raggiungibile per %s->%s: %s", currency, base_currency, exc)
            continue
        if quote is None:
            continue
        await fx_rate_service.upsert_rate(db, currency, base_currency, quote.as_of, quote.rate, source)
        updated += 1
        updated += await _backfill_fx_history(db, provider, currency, base_currency, source)
    return updated


# Copertura minima oltre la quale non ha senso richiedere di nuovo l'intero
# storico ("Max") ogni giorno: se la riga piu' vecchia gia' salvata risale a
# piu' di due anni fa, la coppia e' considerata sufficientemente storicizzata.
_FX_HISTORY_COVERAGE_DAYS = 730


async def _backfill_fx_history(
    db: AsyncSession, provider, from_currency: str, to_currency: str, source: str
) -> int:
    """Scarica lo storico completo del cambio (non solo il tasso di OGGI,
    gia' gestito sopra) la prima volta che una coppia valuta viene vista —
    bug reale osservato dall'utente: cambiando `base_currency`, ogni
    transazione/posizione PASSATA restava senza un tasso applicabile (la
    conversione cerca il tasso non piu' recente della data della riga,
    `fx_rate_expr`/`get_rate`: un solo tasso datato oggi non copre nessuna
    transazione precedente) — le sezioni entrate/uscite e i grafici storici
    risultavano completamente vuoti, non solo "parzialmente incompleti".
    Richiamato ad ogni refresh ma innocuo se la copertura c'e' gia'
    (`_FX_HISTORY_COVERAGE_DAYS`), per non rifare un fetch "Max" ogni giorno
    una volta storicizzata la coppia."""
    earliest = (
        await db.execute(
            select(func.min(FxRate.rate_date)).where(
                FxRate.from_currency == from_currency, FxRate.to_currency == to_currency
            )
        )
    ).scalar_one_or_none()
    if earliest is not None and earliest <= date.today() - timedelta(days=_FX_HISTORY_COVERAGE_DAYS):
        return 0
    try:
        points = await provider.fetch_fx_history(from_currency, to_currency, "Max")
    except MarketDataProviderError as exc:
        logger.warning("storico cambio non raggiungibile per %s->%s: %s", from_currency, to_currency, exc)
        return 0
    if not points:
        return 0
    for point in points:
        await fx_rate_service.upsert_rate(db, from_currency, to_currency, point.at.date(), point.price, source)
    return len(points)


async def list_workspace_owners() -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Enumerazione via la funzione SECURITY DEFINER `list_workspace_owners()`
    (migration 0010): nessuna identita' RLS impostata su questa sessione,
    ma non serve — la funzione gira con i privilegi di `lumio_rls_helper`
    indipendentemente da chi la chiama (vedi il suo commento in migration)."""
    async with async_session_factory() as session:
        rows = (await session.execute(text("SELECT * FROM list_workspace_owners()"))).all()
    return [(row.workspace_id, row.owner_user_id) for row in rows]


async def _cleanup_intraday_quotes(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    """Retention (docs/SPEC_STOCK_PRICE.md): le osservazioni intraday servono
    solo al grafico del giorno corrente, mai uno storico a lungo termine —
    gira ad ogni ciclo (cron o trigger manuale/automatico) indipendentemente
    dal profilo attivo, cosi' righe rimaste da un provider disattivato in
    seguito non si accumulano all'infinito.

    NESSUN commit qui (RLS gotcha noto: `SET LOCAL app.current_user_id`
    scade al commit — un commit intermedio qui perderebbe l'identita' RLS
    per il resto di `_refresh_workspace`, es. la successiva
    `get_active_profile`). Il commit resta a carico del chiamante
    (`refresh_market_data_job`/`refresh_market_data_for_workspace`), che lo
    fa gia' una sola volta a fine ciclo."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_INTRADAY_QUOTE_RETENTION_DAYS)
    await db.execute(
        AssetPriceQuote.__table__.delete().where(
            AssetPriceQuote.workspace_id == workspace_id, AssetPriceQuote.quoted_at < cutoff
        )
    )


async def _refresh_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> RefreshSummary:
    await _cleanup_intraday_quotes(db, workspace_id)

    profile = await get_active_profile(db, workspace_id)
    if profile is None or profile.provider == "manual":
        return RefreshSummary(checked=0, updated=0)  # market data disabilitato o solo manuale: nulla da scaricare

    provider = build_provider(profile)
    # docs/SPEC_STOCK_PRICE.md: solo gli asset con almeno una posizione
    # ANCORA aperta (quantity != 0) — stesso filtro gia' canonico in
    # portfolio_analytics.list_position_valuations(include_closed=False).
    # Un asset senza posizione aperta (venduto per intero, mai posseduto)
    # non serve a nessuna valorizzazione corrente: scaricarne comunque il
    # prezzo sarebbe solo una chiamata sprecata al provider (e un rischio di
    # rate-limit in piu', vedi yahoo.py). Una sola query (EXISTS), niente N+1.
    assets = (
        await db.execute(
            select(Asset).where(
                Asset.workspace_id == workspace_id,
                or_(Asset.symbol.is_not(None), Asset.isin.is_not(None)),
                Asset.id.in_(
                    select(Position.asset_id).where(
                        Position.workspace_id == workspace_id, Position.quantity != 0
                    )
                ),
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

    base_currency = (await db.execute(select(Workspace.base_currency).where(Workspace.id == workspace_id))).scalar_one()
    fx_updated = await _refresh_fx_rates(db, workspace_id, provider, base_currency, profile.provider)

    return RefreshSummary(checked=len(assets), updated=updated, fx_updated=fx_updated)


async def refresh_market_data_job(ctx) -> None:
    # Pagina Impostazioni > Job (jobs.market_data_refresh.enabled): riguarda
    # SOLO l'esecuzione automatica schedulata — il trigger manuale
    # (`refresh_market_data_for_workspace`, bottone "Aggiorna ora") resta
    # sempre disponibile indipendentemente da questo flag, non e' influenzato
    # da questa guardia.
    if not await is_job_enabled(JOB_KIND):
        logger.info("refresh prezzi: cron disattivato da configurazione, nessuna esecuzione automatica")
        return
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

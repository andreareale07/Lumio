"""Job di backfill dello storico patrimonio (FETTA 3, "storico patrimonio
ricostruito") — orchestratore delle fasi (prezzi storici -> FX storico ->
calcolo in memoria -> scrittura a chunk), innescato automaticamente a fine
import (`worker/jobs/import_job.py`, `api/v1/imports.py`) e manualmente da
`POST /portfolios/snapshots/backfill`.

Principio guida (invariato): NULLA cambia per lo snapshot di OGGI —
`write_daily_snapshots`/`snapshot_job` (cron delle 03:00) restano intatti.
Questo job scrive un secondo percorso, SOLO-STORICO, che non passa mai da
`compute_valuation` (vedi il docstring di
`portfolio_analytics.compute_net_worth_backfill_series` per il perche').

Regola di sessione (`SET LOCAL app.current_user_id` scade al commit, vedi
`app/db/rls.py`): OGNI fase apre la SUA sessione RLS fresca, mai un commit
dentro una sessione riusata da un'altra fase. La fase prezzi apre perfino
una sessione PER ASSET (le chiamate HTTP durano secondi, rate limiting
incluso — mai tenerle dentro una transazione DB aperta a lungo).
`tracked_job_run` apre gia' le proprie sessioni per registrare
'running'/'success'/'failed', indipendenti da tutte queste.

Nessun `_job_id` fisso in `enqueue_snapshot_backfill` (worker/queue.py): il
doppio scatto (bottone premuto due volte, o trigger automatico + manuale in
rapida successione) e' gestito qui sopra, in
`api/v1/portfolios.py::trigger_snapshot_backfill`, controllando lo stato in
`job_runs` PRIMA di accodare — stesso principio di
`trigger_snapshot_rebuild`/`trigger_reclassification`."""
import asyncio
import logging
import uuid
from datetime import date

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.rls import rls_session
from app.marketdata.base import MarketDataProviderError
from app.marketdata.registry import build_provider
from app.models.investment_transaction import InvestmentTransaction
from app.models.transaction import Transaction
from app.services import job_events
from app.services.analytics import resolve_currency
from app.services.job_run_tracker import tracked_job_run
from app.services.market_data_profile_service import get_active_profile
from app.services.portfolio_analytics import compute_net_worth_backfill_series, upsert_net_worth_backfill_chunk
from app.services.price_history_backfill import (
    MAX_CONSECUTIVE_PROVIDER_ERRORS,
    PriceBackfillSummary,
    backfill_fx_history,
    backfill_one_asset_price,
    list_price_backfill_targets,
)

logger = logging.getLogger("lumio.worker.snapshot_backfill_job")

JOB_KIND = "snapshot_backfill"
NAMESPACE = "snapshot_backfill"
# Chunk di scrittura (§3.4 del piano): abbastanza piccolo da tenere ogni
# transazione RLS breve anche per un backfill di 10 anni (~3.650 righe),
# abbastanza grande da non moltiplicare i round-trip per nulla.
_WRITE_CHUNK_SIZE = 180


async def _resolve_date_range(
    workspace_id: uuid.UUID, user_id: uuid.UUID, requested_date_from: date | None
) -> tuple[date, date, bool]:
    """'Sessione A' del job: valuta il range da ricostruire.

    Fine SEMPRE `date.today()` (mai un parametro: l'ultimo punto del grafico
    deve sempre coincidere con la KPI "Patrimonio" accanto, §3.1). Inizio =
    `requested_date_from` se dato (trigger da import, gia' scoped a
    `import_row.period_start` — un re-import di un mese ricalcola solo quel
    mese, MAI un download decennale), altrimenti
    `LEAST(MIN(transactions.transaction_date), MIN(investment_transactions.
    trade_date))` dell'intero workspace (trigger manuale "Ricostruisci
    storico"), clampato a `snapshot_backfill_max_years` — una data digitata
    male (o un `period_start` corrotto) non deve generare decine di
    migliaia di righe. Ritorna anche se il clamp e' scattato, per
    dichiararlo onestamente in `run.message`."""
    date_to = date.today()
    async with rls_session(user_id) as db:
        if requested_date_from is not None:
            earliest = requested_date_from
        else:
            result = await db.execute(
                select(
                    func.least(
                        select(func.min(Transaction.transaction_date))
                        .where(Transaction.workspace_id == workspace_id)
                        .scalar_subquery(),
                        select(func.min(InvestmentTransaction.trade_date))
                        .where(InvestmentTransaction.workspace_id == workspace_id)
                        .scalar_subquery(),
                    )
                )
            )
            earliest = result.scalar_one_or_none() or date_to

    max_years = get_settings().snapshot_backfill_max_years
    try:
        floor_date = date_to.replace(year=date_to.year - max_years)
    except ValueError:
        # 29 febbraio, l'anno clampato non e' bisestile: nessun'altra data
        # valida di riferimento se non il 28.
        floor_date = date_to.replace(year=date_to.year - max_years, day=28)
    clamped = earliest < floor_date
    resolved_from = max(earliest, floor_date)
    return resolved_from, date_to, clamped


async def _run_price_phase(workspace_id: uuid.UUID, user_id: uuid.UUID, date_to: date) -> PriceBackfillSummary:
    """Fase prezzi: una sessione RLS di sola lettura per l'elenco target
    ('sessione A' per questa sotto-fase), poi UNA sessione RLS FRESCA per
    OGNI asset (fetch HTTP + upsert + commit + chiusura) — mai il job
    intero interrotto da un provider in errore su un solo asset (DoD M09),
    solo la fase si ferma dopo troppi errori CONSECUTIVI."""
    summary = PriceBackfillSummary()
    async with rls_session(user_id) as db:
        profile = await get_active_profile(db, workspace_id)
        if profile is None or profile.provider == "manual":
            return summary
        provider_name = profile.provider
        targets = await list_price_backfill_targets(db, workspace_id)

    if not targets:
        return summary

    provider = build_provider(profile)
    summary.assets_checked = len(targets)
    consecutive_errors = 0
    delay = get_settings().market_data_backfill_delay_seconds

    for index, target in enumerate(targets, start=1):
        if consecutive_errors >= MAX_CONSECUTIVE_PROVIDER_ERRORS:
            logger.warning(
                "snapshot_backfill: %d errori consecutivi dal provider %s, fase prezzi interrotta "
                "(asset restanti valorizzati a costo storico)",
                consecutive_errors,
                provider_name,
            )
            break
        try:
            async with rls_session(user_id) as db:
                updated = await backfill_one_asset_price(
                    db, workspace_id, provider, provider_name, target, date_to
                )
                await db.commit()
            if updated:
                summary.assets_updated += 1
            consecutive_errors = 0
        except MarketDataProviderError as exc:
            logger.warning("snapshot_backfill: prezzi non riusciti per asset %s: %s", target.asset.id, exc)
            summary.assets_errors += 1
            consecutive_errors += 1
        await job_events.emit(
            workspace_id,
            "job.progress",
            namespace=NAMESPACE,
            processed=index,
            total=len(targets),
            detail="prices",
        )
        await asyncio.sleep(delay)

    return summary


async def _run_fx_phase(workspace_id: uuid.UUID, user_id: uuid.UUID, currency: str, date_from: date) -> int:
    """Fase FX: UNA sessione RLS per l'intera fase (a differenza della fase
    prezzi, qui non ci sono asset multipli con provider potenzialmente
    fragile per ciascuno — solo poche valute per workspace, la stessa
    granularita' di `market_data.py::_refresh_fx_rates`)."""
    async with rls_session(user_id) as db:
        updated = await backfill_fx_history(db, workspace_id, currency, date_from)
        await db.commit()
    await job_events.emit(workspace_id, "job.progress", namespace=NAMESPACE, processed=1, total=1, detail="fx")
    return updated


async def _compute_and_write(
    workspace_id: uuid.UUID, user_id: uuid.UUID, currency: str, date_from: date, date_to: date
) -> tuple[int, bool]:
    """'Sessione B' (calcolo, zero I/O di scrittura, chiude) + fase
    scrittura (chunk di `_WRITE_CHUNK_SIZE` date, sessione RLS fresca per
    chunk, upsert bulk `ON CONFLICT`, commit, chiude). Tutto cio' che
    attraversa il confine fra le due e' Python puro (`date`, `Decimal`,
    dataclass) — nessuna istanza ORM staccata esce dalla sessione B."""
    async with rls_session(user_id) as db:
        series = await compute_net_worth_backfill_series(db, workspace_id, date_from, date_to, currency)

    has_unconverted = any(day.has_unconverted for day in series)
    total = len(series)
    written = 0
    for start in range(0, total, _WRITE_CHUNK_SIZE):
        chunk = series[start : start + _WRITE_CHUNK_SIZE]
        async with rls_session(user_id) as db:
            await upsert_net_worth_backfill_chunk(db, workspace_id, currency, chunk)
            await db.commit()
        written += len(chunk)
        await job_events.emit(
            workspace_id, "job.progress", namespace=NAMESPACE, processed=written, total=total, detail="snapshots"
        )
    return written, has_unconverted


def _summary_message(
    resolved_from: date, resolved_to: date, clamped: bool, written: int,
    price_summary: PriceBackfillSummary, fx_updated: int, has_unconverted: bool,
) -> str:
    parts = [
        f"Storico ricostruito dal {resolved_from.isoformat()} al {resolved_to.isoformat()} ({written} giorni)."
    ]
    if clamped:
        parts.append(f"Intervallo limitato a {get_settings().snapshot_backfill_max_years} anni.")
    if price_summary.assets_updated or price_summary.assets_errors:
        detail = f"{price_summary.assets_updated} asset con prezzi storici aggiornati"
        if price_summary.assets_errors:
            detail += f", {price_summary.assets_errors} non raggiungibili"
        parts.append(detail + ".")
    if fx_updated:
        parts.append(f"{fx_updated} tassi di cambio storici aggiornati.")
    if has_unconverted:
        parts.append("Alcuni giorni non sono convertibili per mancanza di un tasso di cambio a quella data.")
    return " ".join(parts)


async def snapshot_backfill_job(
    ctx, workspace_id: str, user_id: str, date_from: str | None = None
) -> None:
    """Entry point arq (`worker/queue.py::enqueue_snapshot_backfill`).
    `date_from=None` = "ricostruisci tutto" (trigger manuale); una stringa
    ISO = scope esplicito (trigger automatico a fine import, gia' scoped a
    `import_row.period_start` — vedi `worker/jobs/import_job.py`)."""
    ws_id = uuid.UUID(workspace_id)
    uid = uuid.UUID(user_id)
    requested_from = date.fromisoformat(date_from) if date_from else None

    async with tracked_job_run(ws_id, uid, JOB_KIND) as run:
        resolved_from, resolved_to, clamped = await _resolve_date_range(ws_id, uid, requested_from)

        async with rls_session(uid) as db:
            currency = await resolve_currency(db, ws_id)

        price_summary = await _run_price_phase(ws_id, uid, resolved_to)
        fx_updated = await _run_fx_phase(ws_id, uid, currency, resolved_from)
        written, has_unconverted = await _compute_and_write(ws_id, uid, currency, resolved_from, resolved_to)

        run.message = _summary_message(
            resolved_from, resolved_to, clamped, written, price_summary, fx_updated, has_unconverted
        )
        await job_events.emit(ws_id, "job.completed", namespace=NAMESPACE, processed=written, total=written)

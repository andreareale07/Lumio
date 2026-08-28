"""Valorizzazione del portfolio e scrittura degli snapshot storici (SPEC
§31, §37) — ponte tra il libro mastro investimenti (`positions`) e
`asset_prices`/`portfolio_snapshots`/`net_worth_snapshots`.

Sistema di valute: una posizione la cui valuta non coincide con quella
richiesta viene CONVERTITA (via `fx_rate_service.get_rate`, tasso alla data
`as_of` — mai il piu' recente in assoluto, un valore storico non e'
ricostruibile a posteriori dal tasso di oggi), non piu' esclusa in
silenzio (limite precedente, M08). Se nessun tasso e' disponibile per la
coppia richiesta, la posizione resta onestamente esclusa dal totale ma il
risultato lo segnala (`has_missing_fx_rate=True`) — mai un'esclusione
invisibile come prima.

Il refresh dei PREZZI (chiamare un `MarketDataProvider`) e' un modulo
separato (`app/worker/jobs/market_data.py`): questo modulo legge sempre da
`asset_prices`, mai da un provider direttamente — una posizione senza un
prezzo disponibile per il giorno richiesto ricade onestamente sul costo
storico (`has_market_data=False` sul risultato), mai un crash (DoD M09:
"l'app funziona anche senza market data provider configurato").
"""
import bisect
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import DateTime as SA_DateTime
from sqlalchemy import case, cast, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.asset_profile import AssetProfile
from app.models.financial_account import FinancialAccount
from app.models.fx_rate import FxRate
from app.models.investment_transaction import InvestmentTransaction
from app.models.net_worth_snapshot import NetWorthSnapshot
from app.models.portfolio import Portfolio
from app.models.portfolio_account import PortfolioAccount
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.position import Position
from app.services import fx_rate_service
from app.services.analytics_calc import generate_buckets
from app.services.investment_strategy import STRATEGY_LABELS
from app.services.live_quote_service import LiveQuote
from app.services.position_calc import PositionState, compute_position

# Import locale (dentro write_daily_snapshots, non qui a livello modulo):
# `analytics.py` chiama `compute_valuation` per popolare `investment_total`
# (M09b) — un import a livello modulo in entrambe le direzioni creerebbe un
# ciclo. Nessun impatto a runtime, Python risolve gli import lazy dentro una
# funzione al primo utilizzo.


@dataclass
class PortfolioValuation:
    currency: str
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool
    has_holdings: bool
    # Sistema di valute: True se almeno una posizione in valuta diversa da
    # `currency` non ha potuto essere convertita (nessun tasso disponibile
    # per la coppia/data) ed e' quindi esclusa dal totale — mai
    # un'esclusione silenziosa, il chiamante la segnala in UI.
    has_missing_fx_rate: bool = False


@dataclass
class AllocationItem:
    key: str
    label: str
    value: Decimal
    share: Decimal


@dataclass
class PortfolioAllocation:
    currency: str
    has_market_data: bool
    has_missing_fx_rate: bool
    by_asset_type: list[AllocationItem]
    by_asset: list[AllocationItem]
    by_account: list[AllocationItem]
    # Sistema di valute: ogni posizione raggruppata per la SUA valuta
    # originale (`key`/`label` = codice valuta, es. "USD"), ma il `value` e'
    # gia' convertito in `currency` — cosi' la somma delle fette torna col
    # totale aggregato, e la UI puo' comunque mostrare "USD 9.800 (≈8.950
    # EUR)" invece di un unico numero opaco (Step C-bis).
    by_currency: list[AllocationItem]
    # PAC vs Investimenti (rework dashboard interattivo) — a differenza delle
    # altre 3 distribuzioni e' un valore di COSTO, non di mercato ("quanto ho
    # attualmente investito", non "quanto vale oggi"): il totale coincide
    # quindi con `by_asset_type` solo in assenza di plus/minusvalenze non
    # realizzate. E' comunque legato alle sole posizioni APERTE: un asset
    # venduto per intero smette di contribuire (vedi
    # `_compute_strategy_breakdown`/`position_calc.compute_position`), un
    # riacquisto successivo dello stesso asset riparte pulito senza ereditare
    # il capitale di un ciclo gia' chiuso. Attribuzione per lotto d'acquisto
    # (necessaria per un calcolo fiscale FIFO) resta fuori scope qui: dentro
    # una posizione ancora aperta, una vendita parziale scala tutte le
    # strategie gia' presenti in proporzione, senza distinguere quali unita'
    # specifiche sono state vendute (nessuna identita' di lotto, stesso
    # principio del costo medio ponderato usato ovunque in questo modulo).
    by_strategy: list[AllocationItem]


async def _latest_price(
    db: AsyncSession, workspace_id: uuid.UUID, asset_id: uuid.UUID, as_of: date
) -> AssetPrice | None:
    result = await db.execute(
        select(AssetPrice)
        .where(
            AssetPrice.workspace_id == workspace_id,
            AssetPrice.asset_id == asset_id,
            AssetPrice.price_date <= as_of,
        )
        .order_by(AssetPrice.price_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def compute_valuation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    as_of: date,
    currency: str,
) -> PortfolioValuation:
    """`account_ids=None` valorizza TUTTE le posizioni del workspace (vista
    implicita "tutti i conti", SPEC §36) — un set specifico valorizza solo
    le posizioni sui conti di un portfolio nominato."""
    query = select(Position).where(Position.workspace_id == workspace_id)
    if account_ids is not None:
        # `.in_(set())` su un portfolio senza conti associati e' voluto: deve
        # valorizzare zero posizioni, non tutte (SQLAlchemy gestisce un IN
        # vuoto correttamente, solo con un warning innocuo in log).
        query = query.where(Position.financial_account_id.in_(account_ids))
    positions = list((await db.execute(query)).scalars().all())

    market_value = cost_basis = unrealized_pl = realized_pl = Decimal("0")
    has_market_data = True
    has_holdings = False
    has_missing_fx_rate = False
    for position in positions:
        fx_rate = await fx_rate_service.get_rate(db, position.currency, currency, as_of)
        if fx_rate is None:
            if position.quantity != 0:
                has_missing_fx_rate = True
            continue
        if position.quantity != 0:
            has_holdings = True
        position_cost = position.quantity * position.average_cost * fx_rate
        cost_basis += position_cost
        realized_pl += position.realized_pl * fx_rate

        price_row = await _latest_price(db, workspace_id, position.asset_id, as_of)
        price_fx_rate = (
            await fx_rate_service.get_rate(db, price_row.currency, currency, as_of)
            if price_row is not None
            else None
        )
        if price_row is not None and price_fx_rate is not None:
            position_market_value = position.quantity * price_row.price * price_fx_rate
            market_value += position_market_value
            unrealized_pl += position_market_value - position_cost
        else:
            market_value += position_cost  # fallback onesto a costo storico
            if position.quantity != 0:
                has_market_data = False

    # Quantizzazione a 2 decimali (convenzione monetaria di tutto il resto
    # dell'app, es. Transaction.amount Numeric(18,2)): `quantity` e
    # `average_cost`/`price` hanno scale diverse (Numeric(28,10)/(18,6)),
    # quindi il loro prodotto ha 16 decimali — senza questo passaggio la
    # risposta API mostrerebbe "1200.0000000000000000" invece di "1200.00".
    cents = Decimal("0.01")
    return PortfolioValuation(
        currency=currency,
        market_value=market_value.quantize(cents),
        cost_basis=cost_basis.quantize(cents),
        unrealized_pl=unrealized_pl.quantize(cents),
        realized_pl=realized_pl.quantize(cents),
        has_market_data=has_market_data,
        has_holdings=has_holdings,
        has_missing_fx_rate=has_missing_fx_rate,
    )


@dataclass
class PortfolioSummary:
    portfolio_id: uuid.UUID
    name: str
    account_count: int
    currency: str
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    has_market_data: bool
    has_holdings: bool


async def list_portfolio_summaries(
    db: AsyncSession, workspace_id: uuid.UUID, as_of: date, currency: str
) -> list[PortfolioSummary]:
    """Riepilogo di OGNI `Portfolio` del workspace in una sola risposta —
    per la lista della Panoramica Investimenti (redesign): evita N chiamate
    separate lato client, una per portfolio. Riusa `compute_valuation` in
    un loop, stesso principio gia' in uso in `list_position_valuations`/
    `get_asset_valuation` (un giro per riga, mai una query aggregata
    speciale) — il numero di portfolio di un utente reale e' tipicamente
    una manciata, non centinaia, quindi non serve altro."""
    portfolios = list(
        (
            await db.execute(
                select(Portfolio).where(Portfolio.workspace_id == workspace_id).order_by(Portfolio.name)
            )
        )
        .scalars()
        .all()
    )
    if not portfolios:
        return []

    summaries: list[PortfolioSummary] = []
    for portfolio in portfolios:
        links = (
            await db.execute(
                select(PortfolioAccount.financial_account_id).where(
                    PortfolioAccount.workspace_id == workspace_id,
                    PortfolioAccount.portfolio_id == portfolio.id,
                )
            )
        ).scalars().all()
        account_ids = set(links)
        valuation = await compute_valuation(db, workspace_id, account_ids, as_of, currency)
        summaries.append(
            PortfolioSummary(
                portfolio_id=portfolio.id,
                name=portfolio.name,
                account_count=len(account_ids),
                currency=valuation.currency,
                market_value=valuation.market_value,
                cost_basis=valuation.cost_basis,
                unrealized_pl=valuation.unrealized_pl,
                has_market_data=valuation.has_market_data,
                has_holdings=valuation.has_holdings,
            )
        )
    return summaries


async def compute_allocation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    as_of: date,
    currency: str,
) -> PortfolioAllocation:
    """Distribuzione per tipo/asset/conto/valuta (SPEC §37) — stessa fonte di
    `compute_valuation` (posizioni + `asset_prices`), raggruppata invece che
    sommata in un totale unico. Solo le posizioni con quantita' != 0 entrano
    nella distribuzione — una posizione azzerata non ha piu' senso in un
    donut di allocation. Una posizione in valuta diversa da `currency` viene
    convertita (vedi `compute_valuation`), non piu' esclusa."""
    by_strategy = await _compute_strategy_breakdown(db, workspace_id, account_ids, as_of, currency)

    query = select(Position).where(Position.workspace_id == workspace_id)
    if account_ids is not None:
        query = query.where(Position.financial_account_id.in_(account_ids))
    positions = list((await db.execute(query)).scalars().all())
    relevant = [p for p in positions if p.quantity != 0]

    if not relevant:
        return PortfolioAllocation(
            currency=currency,
            has_market_data=True,
            has_missing_fx_rate=False,
            by_asset_type=[],
            by_asset=[],
            by_account=[],
            by_currency=[],
            by_strategy=by_strategy,
        )

    asset_ids = {p.asset_id for p in relevant}
    assets = {
        a.id: a for a in (await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all()
    }
    account_ids_needed = {p.financial_account_id for p in relevant}
    accounts = {
        a.id: a
        for a in (
            await db.execute(select(FinancialAccount).where(FinancialAccount.id.in_(account_ids_needed)))
        )
        .scalars()
        .all()
    }

    values_by_asset_type: dict[str, Decimal] = {}
    values_by_asset: dict[uuid.UUID, Decimal] = {}
    values_by_account: dict[uuid.UUID, Decimal] = {}
    values_by_currency: dict[str, Decimal] = {}
    has_market_data = True
    has_missing_fx_rate = False
    total = Decimal("0")

    for position in relevant:
        fx_rate = await fx_rate_service.get_rate(db, position.currency, currency, as_of)
        if fx_rate is None:
            has_missing_fx_rate = True
            continue

        price_row = await _latest_price(db, workspace_id, position.asset_id, as_of)
        price_fx_rate = (
            await fx_rate_service.get_rate(db, price_row.currency, currency, as_of)
            if price_row is not None
            else None
        )
        if price_row is not None and price_fx_rate is not None:
            value = position.quantity * price_row.price * price_fx_rate
        else:
            value = position.quantity * position.average_cost * fx_rate
            has_market_data = False
        total += value
        asset = assets.get(position.asset_id)
        if asset is not None:
            values_by_asset_type[asset.asset_type] = (
                values_by_asset_type.get(asset.asset_type, Decimal("0")) + value
            )
        values_by_asset[position.asset_id] = values_by_asset.get(position.asset_id, Decimal("0")) + value
        values_by_account[position.financial_account_id] = (
            values_by_account.get(position.financial_account_id, Decimal("0")) + value
        )
        values_by_currency[position.currency] = values_by_currency.get(position.currency, Decimal("0")) + value

    def _to_items(values: dict, label_fn) -> list[AllocationItem]:
        cents = Decimal("0.01")
        fraction = Decimal("0.0001")
        items = [
            AllocationItem(
                key=str(key),
                label=label_fn(key),
                value=value.quantize(cents),
                share=(value / total).quantize(fraction) if total != 0 else Decimal("0"),
            )
            for key, value in values.items()
        ]
        items.sort(key=lambda item: item.value, reverse=True)
        return items

    return PortfolioAllocation(
        currency=currency,
        has_market_data=has_market_data,
        has_missing_fx_rate=has_missing_fx_rate,
        by_asset_type=_to_items(values_by_asset_type, lambda k: k),
        by_asset=_to_items(
            values_by_asset, lambda k: (assets[k].symbol or assets[k].name) if k in assets else "—"
        ),
        by_account=_to_items(values_by_account, lambda k: accounts[k].name if k in accounts else "—"),
        by_currency=_to_items(values_by_currency, lambda k: k),
        by_strategy=by_strategy,
    )


async def _compute_strategy_breakdown(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    as_of: date,
    currency: str,
) -> list[AllocationItem]:
    """Quanto ho ATTUALMENTE investito (costo, non valore di mercato) nelle
    posizioni ancora aperte, ripartito per strategia (PAC vs una tantum) —
    rilegge l'intero libro mastro per (conto, asset) con lo stesso motore di
    `position_service.recompute_position` (`position_calc.compute_position`),
    non una somma grezza di tutti i "buy" mai fatti. Bug reale corretto: un
    asset comprato e poi venduto per intero continuava a contare nel totale
    "Investimenti" anche a posizione chiusa, disallineando il totale rispetto
    a "Per tipo di strumento" (che vede solo le posizioni aperte) — ora il
    costo di un ciclo gia' chiuso si azzera insieme all'average_cost, stessa
    garanzia gia' testata per il costo medio (vedi test_position_calc.py)."""
    query = select(InvestmentTransaction).where(InvestmentTransaction.workspace_id == workspace_id)
    if account_ids is not None:
        query = query.where(InvestmentTransaction.financial_account_id.in_(account_ids))
    rows = (
        await db.execute(
            query.order_by(
                InvestmentTransaction.financial_account_id,
                InvestmentTransaction.asset_id,
                InvestmentTransaction.trade_date,
                InvestmentTransaction.created_at,
                InvestmentTransaction.id,
            )
        )
    ).scalars().all()

    # L'ORDER BY sopra clusterizza gia' ogni gruppo (conto, asset) in ordine
    # cronologico al suo interno: nessun re-sort necessario qui.
    groups: dict[tuple[uuid.UUID, uuid.UUID], list[InvestmentTransaction]] = {}
    for row in rows:
        if row.asset_id is None:
            continue  # movimento di cassa puro (deposit/withdrawal/fee), nessun asset a cui attribuirlo
        groups.setdefault((row.financial_account_id, row.asset_id), []).append(row)

    totals: dict[str, Decimal] = {}
    for movements in groups.values():
        fx_rate = await fx_rate_service.get_rate(db, movements[0].currency, currency, as_of)
        if fx_rate is None:
            continue
        state = compute_position(movements)
        for strategy, cost in state.strategy_cost.items():
            totals[strategy] = totals.get(strategy, Decimal("0")) + cost * fx_rate

    total_all = sum(totals.values(), Decimal("0"))
    cents = Decimal("0.01")
    fraction = Decimal("0.0001")
    items = [
        AllocationItem(
            key=key,
            label=STRATEGY_LABELS[key],
            value=value.quantize(cents),
            share=(value / total_all).quantize(fraction) if total_all != 0 else Decimal("0"),
        )
        for key, value in totals.items()
    ]
    items.sort(key=lambda item: item.value, reverse=True)
    return items


async def _upsert_portfolio_snapshot(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    snapshot_date: date,
    valuation: PortfolioValuation,
) -> None:
    query = select(PortfolioSnapshot).where(
        PortfolioSnapshot.workspace_id == workspace_id,
        PortfolioSnapshot.snapshot_date == snapshot_date,
    )
    query = query.where(
        PortfolioSnapshot.portfolio_id == portfolio_id
        if portfolio_id is not None
        else PortfolioSnapshot.portfolio_id.is_(None)
    )
    snapshot = (await db.execute(query)).scalar_one_or_none()
    if snapshot is None:
        snapshot = PortfolioSnapshot(
            workspace_id=workspace_id, portfolio_id=portfolio_id, snapshot_date=snapshot_date
        )
        db.add(snapshot)
    snapshot.currency = valuation.currency
    snapshot.market_value = valuation.market_value
    snapshot.cost_basis = valuation.cost_basis
    snapshot.unrealized_pl = valuation.unrealized_pl
    snapshot.realized_pl = valuation.realized_pl
    snapshot.has_market_data = valuation.has_market_data


async def _upsert_net_worth_snapshot(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    snapshot_date: date,
    currency: str,
    liquidity: Decimal,
    debt: Decimal,
    investments: Decimal,
) -> None:
    result = await db.execute(
        select(NetWorthSnapshot).where(
            NetWorthSnapshot.workspace_id == workspace_id,
            NetWorthSnapshot.snapshot_date == snapshot_date,
        )
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        snapshot = NetWorthSnapshot(workspace_id=workspace_id, snapshot_date=snapshot_date)
        db.add(snapshot)
    snapshot.currency = currency
    snapshot.liquidity = liquidity
    snapshot.debt = debt
    snapshot.investments = investments
    # SPEC §31: Net Worth = Cash + Investments + Other Assets - Liabilities.
    # `debt` e' gia' un saldo con segno (negativo quando si e' in debito,
    # vedi test_analytics.py::test_..._debt_total), quindi si SOMMA cosi'
    # com'e' — sottrarlo di nuovo raddoppierebbe l'effetto.
    snapshot.net_worth = liquidity + debt + investments


@dataclass
class SnapshotRunSummary:
    snapshot_date: date
    portfolios: int


async def write_daily_snapshots(
    db: AsyncSession, workspace_id: uuid.UUID, snapshot_date: date | None = None
) -> SnapshotRunSummary:
    """Calcola e scrive (upsert) lo snapshot patrimonio + un portfolio
    snapshot per l'aggregato "tutti i conti" e per ogni portfolio nominato,
    per la data indicata (default oggi). Il chiamante e' responsabile del
    commit — stesso principio di `position_service.py`."""
    from app.services.analytics import account_balances, resolve_currency  # import locale, vedi nota di modulo

    snapshot_date = snapshot_date or date.today()
    currency = await resolve_currency(db, workspace_id)

    aggregate = await compute_valuation(db, workspace_id, None, snapshot_date, currency)
    await _upsert_portfolio_snapshot(db, workspace_id, None, snapshot_date, aggregate)

    portfolios = list(
        (await db.execute(select(Portfolio).where(Portfolio.workspace_id == workspace_id))).scalars().all()
    )
    for portfolio in portfolios:
        links = (
            await db.execute(
                select(PortfolioAccount).where(
                    PortfolioAccount.workspace_id == workspace_id,
                    PortfolioAccount.portfolio_id == portfolio.id,
                )
            )
        ).scalars().all()
        account_ids = {link.financial_account_id for link in links}
        valuation = await compute_valuation(db, workspace_id, account_ids, snapshot_date, currency)
        await _upsert_portfolio_snapshot(db, workspace_id, portfolio.id, snapshot_date, valuation)

    balances = await account_balances(db, workspace_id, currency, snapshot_date)
    await _upsert_net_worth_snapshot(
        db,
        workspace_id,
        snapshot_date,
        currency,
        balances.liquidity_total,
        balances.debt_total,
        aggregate.market_value,
    )
    return SnapshotRunSummary(snapshot_date=snapshot_date, portfolios=len(portfolios))


async def list_portfolio_snapshots(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    date_from: date,
    date_to: date,
) -> list[PortfolioSnapshot]:
    """Storico per l'export Google Sheets (`report_builder.py`) — legge dagli
    snapshot gia' scritti (cron/trigger manuale), mai ricalcolato al volo.
    Nessun punto per un giorno in cui lo snapshot non e' ancora stato
    scritto. Il grafico "Andamento del valore" di Investimenti (redesign)
    NON usa piu' questa funzione: vedi `compute_historical_series` sotto,
    che ricostruisce lo storico vero dal libro movimenti invece di leggere
    uno snapshot congelato."""
    query = select(PortfolioSnapshot).where(
        PortfolioSnapshot.workspace_id == workspace_id,
        PortfolioSnapshot.snapshot_date >= date_from,
        PortfolioSnapshot.snapshot_date <= date_to,
    )
    query = query.where(
        PortfolioSnapshot.portfolio_id == portfolio_id
        if portfolio_id is not None
        else PortfolioSnapshot.portfolio_id.is_(None)
    )
    result = await db.execute(query.order_by(PortfolioSnapshot.snapshot_date))
    return list(result.scalars().all())


def _monthly_checkpoints(date_from: date, date_to: date) -> list[date]:
    """Un checkpoint per la fine di ogni mese nell'intervallo, piu' sempre
    `date_to` come ultimo punto anche se il mese e' incompleto — usata per
    gli intervalli lunghi (oltre un anno) dove una granularita' piu' fine
    produrrebbe centinaia di punti solo per essere ri-bucketizzati dal
    frontend."""
    if date_from > date_to:
        return []
    checkpoints: list[date] = []
    cursor = date(date_from.year, date_from.month, 1)
    while cursor <= date_to:
        next_month = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)
        checkpoint = min(next_month - timedelta(days=1), date_to)
        if checkpoint >= date_from:
            checkpoints.append(checkpoint)
        cursor = next_month
    if not checkpoints or checkpoints[-1] != date_to:
        checkpoints.append(date_to)
    return checkpoints


def _historical_checkpoints(date_from: date, date_to: date) -> list[date]:
    """Sceglie la granularita' dei checkpoint in base all'ampiezza
    dell'intervallo richiesto — stessa "gestione temporale" gia' offerta
    per lo storico prezzi di un singolo asset (`RangeSelector`/
    `HISTORY_PRESETS`), qui applicata all'andamento di un intero ambito:
    un intervallo corto con soli punti mensili sarebbe troppo povero (es.
    "1 mese" con un solo punto), uno lungo con punti giornalieri
    produrrebbe centinaia di punti inutili. Sempre `date_to` come ultimo
    punto, anche a cavallo di un passo incompleto."""
    if date_from > date_to:
        return []
    span_days = (date_to - date_from).days
    if span_days > 400:
        return _monthly_checkpoints(date_from, date_to)
    step_days = 1 if span_days <= 45 else 7
    checkpoints: list[date] = []
    cursor = date_from
    while cursor < date_to:
        checkpoints.append(cursor)
        cursor += timedelta(days=step_days)
    checkpoints.append(date_to)
    return checkpoints


def _states_for_checkpoints(
    movements: list[InvestmentTransaction], checkpoints: list[date]
) -> list[tuple[PositionState | None, str | None]]:
    """Stato di posizione (`compute_position`) e valuta nativa ad ogni
    checkpoint, con un unico scan lineare sia sui movimenti sia sui
    checkpoint (entrambi gia' ordinati per data): O(M + C) invece del
    filtro-e-ricalcola-da-zero ad ogni checkpoint (O(C x M)) — usata dal
    backfill storico patrimonio (FETTA 3), dove `checkpoints` e' UNA riga
    per giorno per anni di storico, non solo i pochi checkpoint mensili di
    `_historical_checkpoints`. Uno stato e' riusato verbatim quando nessun
    nuovo movimento e' entrato nel prefisso rispetto al checkpoint
    precedente — portafogli reali operano in pochi giorni l'anno, quindi il
    prefisso resta identico per la stragrande maggioranza dei checkpoint
    giornalieri consecutivi."""
    results: list[tuple[PositionState | None, str | None]] = []
    n = len(movements)
    idx = 0
    cached_len = -1
    cached_state: PositionState | None = None
    cached_currency: str | None = None
    for checkpoint in checkpoints:
        while idx < n and movements[idx].trade_date <= checkpoint:
            idx += 1
        if idx != cached_len:
            if idx == 0:
                cached_state = None
                cached_currency = None
            else:
                relevant = movements[:idx]
                cached_state = compute_position(relevant)
                cached_currency = relevant[-1].currency
            cached_len = idx
        results.append((cached_state, cached_currency))
    return results


async def compute_historical_series(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    date_from: date,
    date_to: date,
    currency: str,
    checkpoints: list[date] | None = None,
) -> list[tuple[date, PortfolioValuation]]:
    """Andamento storico VERO dell'ambito richiesto, per il grafico
    "Andamento del valore" di Investimenti — a differenza di
    `compute_valuation`, che usa sempre la quantita' ATTUALE di `Position`
    (corretta solo per "oggi", motivo per cui `write_daily_snapshots`
    scrive una riga al giorno invece di ricostruire il passato), qui la
    quantita' ad ogni checkpoint e' ricostruita dal libro mastro
    (`compute_position`, la stessa funzione pura di `position_service.py`)
    filtrato a quella data — stesso principio della pagina di dettaglio
    asset, che mostra gia' lo storico prezzi reale, applicato all'intero
    ambito invece che a un singolo asset.

    Funziona per QUALSIASI scope, incluso lo pseudo-gruppo "conti non
    assegnati a un portfolio": non serve una riga di snapshot dedicata
    (che non esiste e non puo' esistere per uno pseudo-gruppo), il libro
    movimenti e' gia' filtrabile per `account_ids` come ovunque altro nel
    redesign (`portfolio_scope.resolve_account_ids`).

    A differenza di uno snapshot scritto una volta (congelato alla data di
    scrittura), un movimento inserito con data passata si riflette
    correttamente su ogni checkpoint da quella data in poi la prossima
    volta che il grafico viene richiesto — proprieta' voluta per un'app
    dove l'utente corregge/backdata i propri movimenti, non un registro
    "chiuso" a fini contabili.

    Prezzi e tassi di cambio sono precaricati UNA volta per l'intero
    intervallo (non una query per checkpoint per posizione, come farebbe
    riusare `_latest_price`/`fx_rate_service.get_rate`): con la granularita'
    giornaliera di `_historical_checkpoints` per intervalli corti, un
    roundtrip DB per checkpoint moltiplicherebbe le query di centinaia di
    volte. La ricerca "ultimo valore non piu' recente di una data" avviene
    quindi in memoria via bisezione su liste gia' ordinate per data.

    Senza un `MarketDataProvider` configurato, nessun prezzo viene trovato:
    il valore ricade sul costo storico (`has_market_data=False`, stesso
    fallback di `compute_valuation`) — l'andamento mostra comunque il
    capitale investito nel tempo, mai vuoto solo perche' manca un provider
    (DoD M09: l'app funziona anche senza).

    `checkpoints` (FETTA 3, storico patrimonio ricostruito): se fornita, usata
    VERBATIM al posto di `_historical_checkpoints` — il backfill storico
    passa una riga per OGNI giorno dell'intervallo (`generate_buckets(...,
    "day")`), non i pochi checkpoint mensili/settimanali pensati per il
    grafico "Andamento del valore". Con `checkpoints=None` (default) il
    comportamento e il risultato sono IDENTICI a prima di questa modifica:
    `/portfolios/analytics/performance` (l'unico consumatore esistente)
    continua a passare `None` e non regredisce."""
    resolved_checkpoints = checkpoints if checkpoints is not None else _historical_checkpoints(date_from, date_to)
    if not resolved_checkpoints:
        return []

    query = select(InvestmentTransaction).where(
        InvestmentTransaction.workspace_id == workspace_id,
        InvestmentTransaction.asset_id.is_not(None),
    )
    if account_ids is not None:
        query = query.where(InvestmentTransaction.financial_account_id.in_(account_ids))
    query = query.order_by(
        InvestmentTransaction.trade_date, InvestmentTransaction.created_at, InvestmentTransaction.id
    )
    transactions = list((await db.execute(query)).scalars().all())

    by_position: dict[tuple[uuid.UUID, uuid.UUID], list[InvestmentTransaction]] = {}
    for txn in transactions:
        by_position.setdefault((txn.financial_account_id, txn.asset_id), []).append(txn)

    asset_ids = {asset_id for (_account_id, asset_id) in by_position}
    prices_by_asset: dict[uuid.UUID, list[AssetPrice]] = {}
    if asset_ids:
        price_rows = list(
            (
                await db.execute(
                    select(AssetPrice)
                    .where(AssetPrice.workspace_id == workspace_id, AssetPrice.asset_id.in_(asset_ids))
                    .order_by(AssetPrice.asset_id, AssetPrice.price_date)
                )
            )
            .scalars()
            .all()
        )
        for row in price_rows:
            prices_by_asset.setdefault(row.asset_id, []).append(row)

    def latest_price(asset_id: uuid.UUID, as_of: date) -> AssetPrice | None:
        rows = prices_by_asset.get(asset_id)
        if not rows:
            return None
        idx = bisect.bisect_right(rows, as_of, key=lambda r: r.price_date) - 1
        return rows[idx] if idx >= 0 else None

    position_currencies = {relevant[-1].currency for relevant in by_position.values() if relevant}
    price_currencies = {row.currency for rows in prices_by_asset.values() for row in rows}
    fx_currencies = (position_currencies | price_currencies) - {currency}
    fx_by_currency: dict[str, list[FxRate]] = {}
    if fx_currencies:
        fx_rows = list(
            (
                await db.execute(
                    select(FxRate)
                    .where(FxRate.to_currency == currency, FxRate.from_currency.in_(fx_currencies))
                    .order_by(FxRate.from_currency, FxRate.rate_date)
                )
            )
            .scalars()
            .all()
        )
        for row in fx_rows:
            fx_by_currency.setdefault(row.from_currency, []).append(row)

    def latest_fx_rate(from_currency: str, as_of: date) -> Decimal | None:
        if from_currency == currency:
            return Decimal("1")
        rows = fx_by_currency.get(from_currency)
        if not rows:
            return None
        idx = bisect.bisect_right(rows, as_of, key=lambda r: r.rate_date) - 1
        return rows[idx].rate if idx >= 0 else None

    cents = Decimal("0.01")
    # Precalcolo per gruppo (conto, asset): stato + valuta ad OGNI
    # checkpoint in O(M + C) invece di rifare `compute_position` da zero
    # C volte per gruppo (vedi `_states_for_checkpoints`) — indispensabile
    # con `checkpoints` giornalieri su anni di storico, innocuo con i pochi
    # checkpoint di `_historical_checkpoints` (stesso risultato, solo piu'
    # veloce anche li').
    states_by_position = {
        key: _states_for_checkpoints(movements, resolved_checkpoints) for key, movements in by_position.items()
    }

    series: list[tuple[date, PortfolioValuation]] = []
    for checkpoint_index, checkpoint in enumerate(resolved_checkpoints):
        market_value = cost_basis = unrealized_pl = realized_pl = Decimal("0")
        has_market_data = True
        has_holdings = False
        has_missing_fx_rate = False

        for (_account_id, asset_id), states in states_by_position.items():
            state, position_currency = states[checkpoint_index]
            if state is None:
                continue
            if state.quantity == 0 and state.realized_pl == 0:
                continue

            fx_rate = latest_fx_rate(position_currency, checkpoint)
            if fx_rate is None:
                if state.quantity != 0:
                    has_missing_fx_rate = True
                continue
            if state.quantity != 0:
                has_holdings = True

            position_cost = state.quantity * state.average_cost * fx_rate
            cost_basis += position_cost
            realized_pl += state.realized_pl * fx_rate

            price_row = latest_price(asset_id, checkpoint)
            price_fx_rate = latest_fx_rate(price_row.currency, checkpoint) if price_row is not None else None
            if price_row is not None and price_fx_rate is not None:
                position_market_value = state.quantity * price_row.price * price_fx_rate
                market_value += position_market_value
                unrealized_pl += position_market_value - position_cost
            else:
                market_value += position_cost
                if state.quantity != 0:
                    has_market_data = False

        series.append(
            (
                checkpoint,
                PortfolioValuation(
                    currency=currency,
                    market_value=market_value.quantize(cents),
                    cost_basis=cost_basis.quantize(cents),
                    unrealized_pl=unrealized_pl.quantize(cents),
                    realized_pl=realized_pl.quantize(cents),
                    has_market_data=has_market_data,
                    has_holdings=has_holdings,
                    has_missing_fx_rate=has_missing_fx_rate,
                ),
            )
        )
    return series


@dataclass
class PositionValuation:
    position_id: uuid.UUID
    asset_id: uuid.UUID
    asset_label: str
    financial_account_id: uuid.UUID
    account_label: str
    quantity: Decimal
    average_cost: Decimal
    currency: str
    currency_native: str
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool


@dataclass
class PositionValuationsResult:
    items: list[PositionValuation]
    has_market_data: bool
    has_missing_fx_rate: bool


async def list_position_valuations(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    as_of: date,
    currency: str,
    include_closed: bool = False,
) -> PositionValuationsResult:
    """P&L per SINGOLA posizione (milestone 10, report Google Sheets; e
    tabella Posizioni del redesign Investimenti — a differenza di
    `compute_valuation`, che e' solo l'aggregato, qui serve rispondere a
    "quanto sto guadagnando/perdendo su QUEL titolo"). Stessa fonte dati e
    stesso fallback a costo storico di `compute_valuation`, solo a grana
    fine invece che sommata in un totale. `include_closed=True` include
    anche le posizioni a quantita' zero (utile solo per mostrarne il P&L
    realizzato residuo, mai un valore di mercato)."""
    query = select(Position).where(Position.workspace_id == workspace_id)
    if not include_closed:
        query = query.where(Position.quantity != 0)
    if account_ids is not None:
        query = query.where(Position.financial_account_id.in_(account_ids))
    relevant = list((await db.execute(query)).scalars().all())
    if not relevant:
        return PositionValuationsResult(items=[], has_market_data=True, has_missing_fx_rate=False)

    asset_ids = {p.asset_id for p in relevant}
    assets = {
        a.id: a for a in (await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all()
    }
    # Nome pulito dal provider (Step 3, `AssetProfile.display_name`), se mai
    # arricchito — MAI `Asset.name`/`symbol` da soli: quello e' il nome
    # grezzo del parser, spesso con suffissi di borsa tedeschi tipo
    # "DL-,0001" (valore nominale), che l'utente ha gia' segnalato come
    # artefatto da nascondere ovunque si mostri un asset (stesso principio
    # gia' applicato in AssetDetailPage/list_assets).
    display_names = dict(
        (
            await db.execute(
                select(AssetProfile.asset_id, AssetProfile.display_name).where(
                    AssetProfile.workspace_id == workspace_id, AssetProfile.asset_id.in_(asset_ids)
                )
            )
        ).all()
    )
    account_row_ids = {p.financial_account_id for p in relevant}
    accounts = {
        a.id: a
        for a in (
            await db.execute(select(FinancialAccount).where(FinancialAccount.id.in_(account_row_ids)))
        )
        .scalars()
        .all()
    }

    cents = Decimal("0.01")
    results: list[PositionValuation] = []
    has_market_data = True
    has_missing_fx_rate = False
    for position in relevant:
        fx_rate = await fx_rate_service.get_rate(db, position.currency, currency, as_of)
        if fx_rate is None:
            # Nessun tasso disponibile per questa valuta: onestamente
            # esclusa dall'elenco, come `compute_valuation` — ma, a
            # differenza di prima, il flag aggregato lo segnala invece di
            # sparire in silenzio (stesso principio gia' corretto altrove
            # in questo modulo per `compute_valuation`/`compute_allocation`).
            has_missing_fx_rate = True
            continue
        cost_basis = position.quantity * position.average_cost * fx_rate
        price_row = await _latest_price(db, workspace_id, position.asset_id, as_of)
        price_fx_rate = (
            await fx_rate_service.get_rate(db, price_row.currency, currency, as_of)
            if price_row is not None
            else None
        )
        if price_row is not None and price_fx_rate is not None:
            market_value = position.quantity * price_row.price * price_fx_rate
            position_has_market_data = True
        else:
            market_value = cost_basis  # fallback onesto a costo storico
            position_has_market_data = False
            if position.quantity != 0:
                has_market_data = False
        asset = assets.get(position.asset_id)
        asset_label = (
            (display_names.get(position.asset_id) or asset.symbol or asset.name) if asset is not None else "—"
        )
        account = accounts.get(position.financial_account_id)
        account_label = account.name if account is not None else "—"
        results.append(
            PositionValuation(
                position_id=position.id,
                asset_id=position.asset_id,
                asset_label=asset_label,
                financial_account_id=position.financial_account_id,
                account_label=account_label,
                quantity=position.quantity,
                average_cost=position.average_cost,
                currency=currency,
                currency_native=position.currency,
                cost_basis=cost_basis.quantize(cents),
                market_value=market_value.quantize(cents),
                unrealized_pl=(market_value - cost_basis).quantize(cents),
                realized_pl=position.realized_pl.quantize(cents),
                has_market_data=position_has_market_data,
            )
        )
    results.sort(key=lambda p: p.market_value, reverse=True)
    return PositionValuationsResult(
        items=results, has_market_data=has_market_data, has_missing_fx_rate=has_missing_fx_rate
    )


@dataclass
class AssetValuation:
    currency: str
    quantity: Decimal
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool
    has_missing_fx_rate: bool
    # Prezzo per unita' (non moltiplicato per `quantity`, disponibile anche
    # senza posizioni aperte): `price` e' convertito in `currency` (None se
    # nessun prezzo o nessun tasso di cambio disponibile), `price_native`/
    # `price_native_currency` sono il dato originale del provider, sempre
    # presenti quando un prezzo esiste — mai persi dietro la conversione
    # (SPEC: l'originale resta sempre disponibile, la UI lo mostra al
    # passaggio del mouse sul prezzo convertito).
    price: Decimal | None = None
    price_native: Decimal | None = None
    price_native_currency: str | None = None
    # docs/SPEC_STOCK_PRICE.md: presenti SOLO quando il prezzo viene da una
    # live-quote (parametro esplicito `live_quote` di `get_asset_valuation`),
    # mai dal prezzo daily canonico — vedi live_quote_service.py.
    price_quoted_at: datetime | None = None
    price_is_live: bool = False
    price_is_stale: bool = False


async def get_asset_valuation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    as_of: date,
    currency: str,
    live_quote: LiveQuote | None = None,
) -> AssetValuation:
    """P&L convertito per UN asset (somma su tutte le posizioni/conti che lo
    detengono) — stessa fonte e stesso fallback onesto a costo storico di
    `compute_valuation`/`list_position_valuations`, qui filtrato a un asset
    invece che a un portfolio. Usato dalla card "Rendimento" del dettaglio
    asset: a differenza del calcolo lato frontend (che mostrava "—" quando
    il prezzo era in una valuta diversa da quella della posizione, es. un
    ISIN giapponese quotato in JPY comprato in EUR), qui la conversione
    passa sempre da `fx_rate_service`, cosi' il rendimento resta visibile —
    dato che l'utente considera troppo importante per sparire silenziosamente.

    `live_quote` (docs/SPEC_STOCK_PRICE.md): opzionale, passato SOLO dal
    dettaglio di un singolo asset (`app/api/v1/assets.py`, via
    `live_quote_service.get_or_refresh_latest_quote`) — quando presente
    sostituisce `_latest_price` per prezzo/market_value/unrealized_pl,
    altrimenti comportamento identico a oggi. Mai passato da
    `compute_valuation`/`compute_allocation`/`list_position_valuations`: la
    valorizzazione bulk e lo storico restano sul solo prezzo daily
    canonico, come richiesto esplicitamente dalla SPEC."""
    positions = list(
        (
            await db.execute(
                select(Position).where(
                    Position.workspace_id == workspace_id,
                    Position.asset_id == asset_id,
                    Position.quantity != 0,
                )
            )
        )
        .scalars()
        .all()
    )

    cents = Decimal("0.01")
    quantity = Decimal("0")
    cost_basis = Decimal("0")
    market_value = Decimal("0")
    realized_pl = Decimal("0")
    has_market_data = True
    has_missing_fx_rate = False

    if live_quote is not None:
        price_native, price_native_currency = live_quote.price, live_quote.currency
    else:
        price_row = await _latest_price(db, workspace_id, asset_id, as_of)
        price_native = price_row.price if price_row is not None else None
        price_native_currency = price_row.currency if price_row is not None else None
    price_fx_rate = (
        await fx_rate_service.get_rate(db, price_native_currency, currency, as_of)
        if price_native_currency is not None
        else None
    )

    for position in positions:
        fx_rate = await fx_rate_service.get_rate(db, position.currency, currency, as_of)
        if fx_rate is None:
            has_missing_fx_rate = True
            continue
        quantity += position.quantity
        position_cost = position.quantity * position.average_cost * fx_rate
        cost_basis += position_cost
        realized_pl += position.realized_pl * fx_rate

        if price_native is not None and price_fx_rate is not None:
            market_value += position.quantity * price_native * price_fx_rate
        else:
            market_value += position_cost
            has_market_data = False

    price = price_native * price_fx_rate if price_native is not None and price_fx_rate is not None else None

    return AssetValuation(
        currency=currency,
        quantity=quantity,
        cost_basis=cost_basis.quantize(cents),
        market_value=market_value.quantize(cents),
        unrealized_pl=(market_value - cost_basis).quantize(cents),
        realized_pl=realized_pl.quantize(cents),
        has_market_data=has_market_data,
        has_missing_fx_rate=has_missing_fx_rate,
        price=price.quantize(cents) if price is not None else None,
        price_native=price_native,
        price_native_currency=price_native_currency,
        price_quoted_at=live_quote.quoted_at if live_quote is not None else None,
        price_is_live=live_quote is not None,
        price_is_stale=live_quote.stale if live_quote is not None else False,
    )


async def list_net_worth_snapshots(
    db: AsyncSession, workspace_id: uuid.UUID, date_from: date, date_to: date
) -> list[NetWorthSnapshot]:
    result = await db.execute(
        select(NetWorthSnapshot)
        .where(
            NetWorthSnapshot.workspace_id == workspace_id,
            NetWorthSnapshot.snapshot_date >= date_from,
            NetWorthSnapshot.snapshot_date <= date_to,
        )
        .order_by(NetWorthSnapshot.snapshot_date)
    )
    return list(result.scalars().all())


def _net_worth_bucket_expr(granularity: str):
    """Stesso schema di `analytics._bucket_expr`, qui su
    `NetWorthSnapshot.snapshot_date` invece di `Transaction.transaction_date`
    — non riusabile direttamente (quella e' legata a `Transaction`), ma
    stessa logica per "semester" (Postgres `date_trunc` non lo conosce, va
    costruito a mano a partire dall'inizio dell'anno)."""
    if granularity == "semester":
        year_start = func.date_trunc("year", cast(NetWorthSnapshot.snapshot_date, SA_DateTime))
        return case(
            (func.extract("month", NetWorthSnapshot.snapshot_date) <= 6, year_start),
            else_=year_start + text("interval '6 months'"),
        )
    return func.date_trunc(granularity, cast(NetWorthSnapshot.snapshot_date, SA_DateTime))


async def list_net_worth_snapshots_downsampled(
    db: AsyncSession, workspace_id: uuid.UUID, granularity: str, date_from: date, date_to: date
) -> list[NetWorthSnapshot]:
    """Downsampling server-side per granularita' larghe (trimestre/anno) —
    serve DA QUESTA FETTA in poi: con lo storico ricostruito (snapshot
    giornalieri per anni, non solo da oggi in poi) una `trendWindow` con
    granularita' 'year' copre gia' 6 anni = 2.190 punti, troppi per un
    grafico e ~500KB di payload. UN punto per bucket — l'ULTIMO
    `snapshot_date` disponibile in quel bucket (`DISTINCT ON`, mai una
    media/interpolazione: il patrimonio a fine trimestre e' il dato che
    l'utente si aspetta di vedere in un punto "trimestre", non un valore
    smussato)."""
    bucket_expr = _net_worth_bucket_expr(granularity)
    bucketed_ids = (
        select(NetWorthSnapshot.id)
        .where(
            NetWorthSnapshot.workspace_id == workspace_id,
            NetWorthSnapshot.snapshot_date >= date_from,
            NetWorthSnapshot.snapshot_date <= date_to,
        )
        .distinct(bucket_expr)
        .order_by(bucket_expr, NetWorthSnapshot.snapshot_date.desc())
        .subquery()
    )
    result = await db.execute(
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.id.in_(select(bucketed_ids.c.id)))
        .order_by(NetWorthSnapshot.snapshot_date)
    )
    return list(result.scalars().all())


# --- Storico patrimonio ricostruito (FETTA 3) -------------------------------
#
# Principio guida (invariato per lo snapshot di OGGI): `write_daily_snapshots`
# resta l'UNICO percorso che passa da `compute_valuation` (quantita' ATTUALI
# di `Position`, corrette solo per "oggi"). Il backfill qui sotto e' un
# secondo percorso, SOLO-STORICO, che non chiama mai `compute_valuation` —
# strutturalmente sbagliata per il passato perche' legge le quantita' attuali
# e usa `as_of` solo per il prezzo (vedi il limite gia' documentato sopra su
# `compute_historical_series`).
#
# Diviso in due funzioni separate (mai un'unica funzione che calcola E
# scrive) per rispettare la regola di sessione del job
# (`worker/jobs/snapshot_backfill.py`, vedi il suo docstring): `SET LOCAL
# app.current_user_id` scade al commit, quindi il job apre una sessione RLS
# fresca per FASE — una per il calcolo (sola lettura, zero I/O di scrittura,
# puo' restare aperta quanto serve) e una per OGNI CHUNK di scrittura (upsert
# + commit + chiusura, mai una transazione lunga tenuta aperta durante il
# calcolo). Nessuna delle due funzioni committa: il chiamante lo fa (stesso
# principio di `write_daily_snapshots`, "il chiamante e' responsabile del
# commit").


@dataclass
class NetWorthBackfillDay:
    """Un giorno della serie storica ricostruita: liquidita'/debiti da
    `analytics.account_balance_history`, investimenti dalla `PortfolioValuation`
    completa di `compute_historical_series` (mai solo `market_value`: servono
    anche `cost_basis`/`unrealized_pl`/`realized_pl` per scrivere l'aggregato
    `portfolio_snapshots`, che ha quelle colonne NOT NULL)."""

    day: date
    liquidity: Decimal
    debt: Decimal
    investments: PortfolioValuation
    has_unconverted: bool


async def compute_net_worth_backfill_series(
    db: AsyncSession, workspace_id: uuid.UUID, date_from: date, date_to: date, currency: str
) -> list[NetWorthBackfillDay]:
    """Fase di calcolo IN MEMORIA (nessuna scrittura, nessun commit) del
    backfill storico patrimonio — 'sessione B' del job
    `snapshot_backfill.py`: carica libro mastro conti (via
    `account_balance_history`, UNA query con window function per tutto lo
    storico) + libro mastro investimenti/prezzi/cambi (via
    `compute_historical_series` con un checkpoint per OGNI giorno
    dell'intervallo, precaricati una volta sola per l'intero range), calcola
    l'intera serie giornaliera, poi ritorna — la sessione chiama questa
    funzione e poi si chiude, mai riusata per la fase di scrittura
    successiva."""
    days = generate_buckets(date_from, date_to, "day")
    if not days:
        return []

    # Import locale: stesso motivo di `write_daily_snapshots` sopra
    # (`analytics.py` importa gia' `compute_valuation` da questo modulo a
    # livello di funzione — un import a livello modulo in entrambe le
    # direzioni creerebbe un ciclo).
    from app.services.analytics import account_balance_history

    liquidity_debt = await account_balance_history(db, workspace_id, currency, date_from, date_to)
    liquidity_by_day = {d.day: d.liquidity for d in liquidity_debt}
    debt_by_day = {d.day: d.debt for d in liquidity_debt}
    unconverted_by_day = {d.day: d.has_unconverted for d in liquidity_debt}

    # `account_ids=None`: TUTTI i conti del workspace (stesso scope implicito
    # di `write_daily_snapshots`/`compute_valuation(..., None, ...)` per
    # l'aggregato "tutti i conti" — i portfolio nominati non hanno un loro
    # backfill, vedi docstring del job).
    investments_series = await compute_historical_series(
        db, workspace_id, None, date_from, date_to, currency, checkpoints=days
    )

    results: list[NetWorthBackfillDay] = []
    for day, valuation in investments_series:
        results.append(
            NetWorthBackfillDay(
                day=day,
                liquidity=liquidity_by_day.get(day, Decimal("0")),
                debt=debt_by_day.get(day, Decimal("0")),
                investments=valuation,
                has_unconverted=unconverted_by_day.get(day, False) or valuation.has_missing_fx_rate,
            )
        )
    return results


async def upsert_net_worth_backfill_chunk(
    db: AsyncSession, workspace_id: uuid.UUID, currency: str, rows: list[NetWorthBackfillDay]
) -> None:
    """Upsert bulk `ON CONFLICT` di un CHUNK di giorni gia' calcolati (mai
    l'intera serie in una volta: il chiamante la spezza in chunk di ~180
    date per tenere ogni sessione/transazione RLS breve, vedi
    `snapshot_backfill.py`) — scrive sia `net_worth_snapshots` sia
    l'aggregato `portfolio_snapshots` (`portfolio_id IS NULL`), la stessa
    invariante testata di `write_daily_snapshots`
    (`net_worth_snapshots.investments == portfolio_snapshots(NULL).market_value`).

    `ON CONFLICT DO UPDATE` invece di SELECT-poi-INSERT (a differenza di
    `_upsert_net_worth_snapshot`/`_upsert_portfolio_snapshot` sopra, ORM-based
    e usate solo dal cron/trigger manuale 'oggi'): elimina la gara con il
    cron delle 03:00 sulla riga di OGGI quando il backfill la riscrive
    (`date_to` include sempre la data odierna, vedi §3.1 del piano) — l'ultimo
    ON CONFLICT a scrivere vince, mai un errore di chiave duplicata. Il
    chiamante e' responsabile del commit (stesso principio di
    `write_daily_snapshots`)."""
    if not rows:
        return
    cents = Decimal("0.01")

    net_worth_values = [
        {
            "workspace_id": workspace_id,
            "snapshot_date": r.day,
            "currency": currency,
            "liquidity": r.liquidity,
            "debt": r.debt,
            "investments": r.investments.market_value,
            # SPEC §31: Net Worth = Cash + Investments - Liabilities. `debt'
            # e' gia' un saldo con segno (negativo quando si e' in debito),
            # si SOMMA cosi' com'e' — stesso principio di
            # `_upsert_net_worth_snapshot` sopra.
            "net_worth": (r.liquidity + r.debt + r.investments.market_value).quantize(cents),
        }
        for r in rows
    ]
    nw_stmt = pg_insert(NetWorthSnapshot).values(net_worth_values)
    nw_stmt = nw_stmt.on_conflict_do_update(
        constraint="uq_net_worth_snapshots_workspace_date",
        set_={
            "currency": nw_stmt.excluded.currency,
            "liquidity": nw_stmt.excluded.liquidity,
            "debt": nw_stmt.excluded.debt,
            "investments": nw_stmt.excluded.investments,
            "net_worth": nw_stmt.excluded.net_worth,
        },
    )
    await db.execute(nw_stmt)

    portfolio_values = [
        {
            "workspace_id": workspace_id,
            "portfolio_id": None,
            "snapshot_date": r.day,
            "currency": currency,
            "market_value": r.investments.market_value,
            "cost_basis": r.investments.cost_basis,
            "unrealized_pl": r.investments.unrealized_pl,
            "realized_pl": r.investments.realized_pl,
            "has_market_data": r.investments.has_market_data,
        }
        for r in rows
    ]
    pf_stmt = pg_insert(PortfolioSnapshot).values(portfolio_values)
    # Nessun vincolo NOMINATO su questa unicita' (indice PARZIALE creato via
    # SQL diretto in migration 0010_market_data.py, `WHERE portfolio_id IS
    # NULL"): `index_elements`+`index_where`, non `constraint=`, e' l'unico
    # modo per cui SQLAlchemy possa individuare un indice parziale come
    # target ON CONFLICT senza un nome di vincolo esplicito.
    pf_stmt = pf_stmt.on_conflict_do_update(
        index_elements=["workspace_id", "snapshot_date"],
        index_where=text("portfolio_id IS NULL"),
        set_={
            "currency": pf_stmt.excluded.currency,
            "market_value": pf_stmt.excluded.market_value,
            "cost_basis": pf_stmt.excluded.cost_basis,
            "unrealized_pl": pf_stmt.excluded.unrealized_pl,
            "realized_pl": pf_stmt.excluded.realized_pl,
            "has_market_data": pf_stmt.excluded.has_market_data,
        },
    )
    await db.execute(pf_stmt)

"""Valorizzazione del portfolio e scrittura degli snapshot storici (SPEC
§31, §37) — ponte tra il libro mastro investimenti (`positions`) e
`asset_prices`/`portfolio_snapshots`/`net_worth_snapshots`.

Principio non negoziabile (stesso di `analytics.py` per M08): NESSUNA
conversione valutaria. Una posizione la cui valuta non coincide con la
valuta richiesta viene semplicemente esclusa dal totale — non e' un errore,
e' lo stesso limite gia' accettato per i saldi conto.

Il refresh dei PREZZI (chiamare un `MarketDataProvider`) e' un modulo
separato (`app/worker/jobs/market_data.py`): questo modulo legge sempre da
`asset_prices`, mai da un provider direttamente — una posizione senza un
prezzo disponibile per il giorno richiesto ricade onestamente sul costo
storico (`has_market_data=False` sul risultato), mai un crash (DoD M09:
"l'app funziona anche senza market data provider configurato").
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.asset_price import AssetPrice
from app.models.financial_account import FinancialAccount
from app.models.investment_transaction import InvestmentTransaction
from app.models.net_worth_snapshot import NetWorthSnapshot
from app.models.portfolio import Portfolio
from app.models.portfolio_account import PortfolioAccount
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.models.position import Position
from app.services.investment_strategy import STRATEGY_LABELS, classify_strategy

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
    by_asset_type: list[AllocationItem]
    by_asset: list[AllocationItem]
    by_account: list[AllocationItem]
    # PAC vs Investimenti (rework dashboard interattivo) — a differenza delle
    # altre 3 distribuzioni, non e' "quanto vale oggi" (valore di mercato
    # delle posizioni correnti: attribuire una posizione attuale alla
    # strategia dell'acquisto originale richiederebbe un tracciamento a lotti,
    # fuori scope) ma "quanto ho investito finora con ciascuna strategia" —
    # una somma sul libro mastro (`InvestmentTransaction`, solo i "buy"),
    # non sulle posizioni derivate.
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
    for position in positions:
        if position.currency != currency:
            continue
        if position.quantity != 0:
            has_holdings = True
        position_cost = position.quantity * position.average_cost
        cost_basis += position_cost
        realized_pl += position.realized_pl

        price_row = await _latest_price(db, workspace_id, position.asset_id, as_of)
        if price_row is not None and price_row.currency == currency:
            position_market_value = position.quantity * price_row.price
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
    )


async def compute_allocation(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    as_of: date,
    currency: str,
) -> PortfolioAllocation:
    """Distribuzione per tipo/asset/conto (SPEC §37) — stessa fonte di
    `compute_valuation` (posizioni + `asset_prices`), raggruppata invece che
    sommata in un totale unico. Solo le posizioni con quantita' != 0 e nella
    valuta richiesta entrano nella distribuzione — una posizione azzerata
    non ha piu' senso in un donut di allocation."""
    by_strategy = await _compute_strategy_breakdown(db, workspace_id, account_ids, currency)

    query = select(Position).where(Position.workspace_id == workspace_id)
    if account_ids is not None:
        query = query.where(Position.financial_account_id.in_(account_ids))
    positions = list((await db.execute(query)).scalars().all())
    relevant = [p for p in positions if p.currency == currency and p.quantity != 0]

    if not relevant:
        return PortfolioAllocation(
            currency=currency,
            has_market_data=True,
            by_asset_type=[],
            by_asset=[],
            by_account=[],
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
    has_market_data = True
    total = Decimal("0")

    for position in relevant:
        price_row = await _latest_price(db, workspace_id, position.asset_id, as_of)
        if price_row is not None and price_row.currency == currency:
            value = position.quantity * price_row.price
        else:
            value = position.quantity * position.average_cost
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
        by_asset_type=_to_items(values_by_asset_type, lambda k: k),
        by_asset=_to_items(
            values_by_asset, lambda k: (assets[k].symbol or assets[k].name) if k in assets else "—"
        ),
        by_account=_to_items(values_by_account, lambda k: accounts[k].name if k in accounts else "—"),
        by_strategy=by_strategy,
    )


async def _compute_strategy_breakdown(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    currency: str,
) -> list[AllocationItem]:
    """Quanto e' stato investito finora con ciascuna strategia (PAC vs una
    tantum) — somma sul libro mastro (`InvestmentTransaction`, solo i
    movimenti "buy": una vendita o un dividendo non sono "investire", vedi
    `app/services/investment_strategy.py`). A differenza delle altre
    distribuzioni di `compute_allocation`, non e' legata alle posizioni
    APERTE: un titolo interamente venduto ha comunque contribuito al totale
    investito in passato."""
    query = select(InvestmentTransaction).where(
        InvestmentTransaction.workspace_id == workspace_id,
        InvestmentTransaction.type == "buy",
        InvestmentTransaction.currency == currency,
    )
    if account_ids is not None:
        query = query.where(InvestmentTransaction.financial_account_id.in_(account_ids))
    rows = (await db.execute(query)).scalars().all()

    totals: dict[str, Decimal] = {}
    for row in rows:
        strategy = classify_strategy(row.source_type_raw)
        totals[strategy] = totals.get(strategy, Decimal("0")) + abs(row.amount)

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
    """Storico per il grafico Performance (SPEC §37) — legge SEMPRE dagli
    snapshot gia' scritti (cron/trigger manuale), mai ricalcolato al volo
    (DoD M09: "non ricalcolato da zero ogni volta"). Nessun punto per un
    giorno in cui lo snapshot non e' ancora stato scritto: lo storico parte
    da quando esiste il primo snapshot, senza tentare di ricostruire il
    passato (decisione di prodotto per M09)."""
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


@dataclass
class PositionValuation:
    asset_id: uuid.UUID
    asset_label: str
    quantity: Decimal
    average_cost: Decimal
    currency: str
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    has_market_data: bool


async def list_position_valuations(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    account_ids: set[uuid.UUID] | None,
    as_of: date,
    currency: str,
) -> list[PositionValuation]:
    """P&L per SINGOLA posizione (milestone 10, report Google Sheets: a
    differenza di `compute_valuation`, che e' solo l'aggregato, qui serve
    rispondere a "quanto sto guadagnando/perdendo su quel titolo"). Stessa
    fonte dati e stesso fallback a costo storico di `compute_valuation`,
    solo a grana fine invece che sommata in un totale."""
    query = select(Position).where(Position.workspace_id == workspace_id, Position.quantity != 0)
    if account_ids is not None:
        query = query.where(Position.financial_account_id.in_(account_ids))
    positions = list((await db.execute(query)).scalars().all())
    relevant = [p for p in positions if p.currency == currency]
    if not relevant:
        return []

    asset_ids = {p.asset_id for p in relevant}
    assets = {
        a.id: a for a in (await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all()
    }

    cents = Decimal("0.01")
    results: list[PositionValuation] = []
    for position in relevant:
        cost_basis = position.quantity * position.average_cost
        price_row = await _latest_price(db, workspace_id, position.asset_id, as_of)
        if price_row is not None and price_row.currency == currency:
            market_value = position.quantity * price_row.price
            has_market_data = True
        else:
            market_value = cost_basis  # fallback onesto a costo storico
            has_market_data = False
        asset = assets.get(position.asset_id)
        label = (asset.symbol or asset.name) if asset is not None else "—"
        results.append(
            PositionValuation(
                asset_id=position.asset_id,
                asset_label=label,
                quantity=position.quantity,
                average_cost=position.average_cost,
                currency=currency,
                cost_basis=cost_basis.quantize(cents),
                market_value=market_value.quantize(cents),
                unrealized_pl=(market_value - cost_basis).quantize(cents),
                realized_pl=position.realized_pl.quantize(cents),
                has_market_data=has_market_data,
            )
        )
    results.sort(key=lambda p: p.market_value, reverse=True)
    return results


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

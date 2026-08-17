"""Logica DB-aware degli analytics (SPEC §30, 31, 39, 44-46, 73), ponte tra
l'API (`app/api/v1/analytics.py`) e le tabelle `financial_accounts` /
`transactions` / `categories` — stessa separazione di `rule_loader.py` per
le regole. La matematica pura (bucket temporali, ricostruzione della serie
storica, periodo di confronto) vive in `app/services/analytics_calc.py`.

Vincolo di prodotto (M08, confermato con l'utente): nessuna conversione
valutaria, in nessun punto di questo modulo. `resolve_currency` e' l'UNICO
posto che decide "quale valuta" per una richiesta — quando arrivera' un
tasso di cambio (con il `MarketDataProvider` di M09) il cambiamento resta
confinato qui piu' un passo di conversione esplicito, non sparso in ogni
query. Nota per M09: un `MarketDataProvider` che esponga solo il tasso
*attuale* non basterebbe per un grafico patrimonio storico multi-valuta —
serve anche lo storico dei tassi, non solo l'ultimo.

Modello del saldo conto (SPEC §18: `financial_accounts` non ha una colonna
`balance`): "ancora + delta". Per ogni conto si prende come ancora
l'ultima transazione con `balance_after` non nullo (non tutte le sorgenti
di import lo popolano, vedi `csv_import.py`) e si somma il delta delle
transazioni successive; se il conto non ha nessuna ancora, il saldo e'
semplicemente la somma di tutte le transazioni (`amount` e' gia' firmato:
negativo per i debiti, vedi `csv_import.py:_resolve_amount_and_direction`).
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Date as SA_Date
from sqlalchemy import DateTime as SA_DateTime
from sqlalchemy import String as SA_String
from sqlalchemy import bindparam, case, cast, func, or_, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.financial_account import FinancialAccount
from app.models.transaction import Transaction
from app.services.analytics_calc import (
    GRANULARITIES,
    generate_buckets,
    previous_period,
    reconstruct_running_series,
)

# Mappatura account_type -> gruppo di patrimonio (decisione di prodotto M08,
# rivista dopo feedback reale dell'utente: molti conti reali — Trade
# Republic, Fineco — sono IBRIDI, spendibili con carta E utilizzabili per
# comprare titoli sullo stesso conto. "brokerage" NON implica quindi "non
# liquido": il saldo di un conto e' sempre e solo quanto cash c'e' sopra
# (un acquisto reale sposterebbe cash fuori dal saldo verso una `position`,
# valorizzata a prezzo di mercato in M09 — mai dedotto dal solo
# account_type). Per questo TUTTI i conti tranne le carte di credito
# contano come Liquidita'. `has_investments`/`investment_total` restano nel
# contratto ma sono sempre False/0 in M08: nessun account_type oggi da'
# diritto a un valore di investimento reale, quel dato arriva con M09
# (posizioni + MarketDataProvider), non da una mappatura statica qui.
LIQUIDITY_ACCOUNT_TYPES = frozenset({"checking", "savings", "brokerage", "cash", "other"})
DEBT_ACCOUNT_TYPES = frozenset({"credit_card"})

_EXCLUDED_FROM_CASH_FLOW = ("transfer", "investment")


@dataclass
class AccountBalanceRow:
    financial_account_id: uuid.UUID
    name: str
    account_type: str
    balance: Decimal


@dataclass
class AccountBalances:
    accounts: list[AccountBalanceRow]
    liquidity_total: Decimal
    debt_total: Decimal
    investment_total: Decimal
    has_investments: bool


@dataclass
class IncomeExpenses:
    income: Decimal
    expenses: Decimal


async def resolve_currency(
    db: AsyncSession, workspace_id: uuid.UUID, requested: str | None = None
) -> str:
    """Unico punto di decisione della valuta per gli analytics (vedi
    docstring di modulo). Se non richiesta esplicitamente, usa la valuta
    prevalente del workspace (quella con piu' conti); "EUR" se il workspace
    non ha ancora nessun conto."""
    if requested:
        return requested.upper()
    result = await db.execute(
        select(FinancialAccount.currency, func.count().label("n"))
        .where(FinancialAccount.workspace_id == workspace_id)
        .group_by(FinancialAccount.currency)
        .order_by(func.count().desc())
        .limit(1)
    )
    row = result.first()
    return row.currency if row else "EUR"


# "Ancora + delta": DISTINCT ON per prendere, per ogni conto, l'ultima riga
# con balance_after non nullo fino a `as_of` (ordinata per data/creazione/id
# per essere deterministica anche con piu' transazioni nello stesso giorno);
# poi si somma il delta delle transazioni successive all'ancora (o di TUTTE
# le transazioni, se il conto non ha nessuna ancora — LEFT JOIN, non INNER).
_ACCOUNT_BALANCES_SQL = text(
    """
    WITH anchors AS (
        SELECT DISTINCT ON (financial_account_id)
            financial_account_id,
            transaction_date AS anchor_date,
            created_at AS anchor_created_at,
            id AS anchor_id,
            balance_after AS anchor_balance
        FROM transactions
        WHERE workspace_id = :workspace_id
          AND balance_after IS NOT NULL
          AND transaction_date <= :as_of
        ORDER BY financial_account_id, transaction_date DESC, created_at DESC, id DESC
    ),
    deltas AS (
        SELECT
            t.financial_account_id AS financial_account_id,
            SUM(t.amount) AS delta_sum
        FROM transactions t
        LEFT JOIN anchors a ON a.financial_account_id = t.financial_account_id
        WHERE t.workspace_id = :workspace_id
          AND t.transaction_date <= :as_of
          AND (
              a.anchor_date IS NULL
              OR (t.transaction_date, t.created_at, t.id)
                 > (a.anchor_date, a.anchor_created_at, a.anchor_id)
          )
        GROUP BY t.financial_account_id
    )
    SELECT
        fa.id AS financial_account_id,
        fa.name AS name,
        fa.account_type AS account_type,
        COALESCE(a.anchor_balance, 0) + COALESCE(d.delta_sum, 0) AS balance
    FROM financial_accounts fa
    LEFT JOIN anchors a ON a.financial_account_id = fa.id
    LEFT JOIN deltas d ON d.financial_account_id = fa.id
    WHERE fa.workspace_id = :workspace_id
      AND fa.currency = :currency
      AND fa.is_active = true
      AND (:financial_account_id IS NULL OR fa.id = :financial_account_id)
    ORDER BY fa.name
    """
).bindparams(
    bindparam("workspace_id", type_=PG_UUID(as_uuid=True)),
    bindparam("as_of", type_=SA_Date),
    bindparam("currency", type_=SA_String),
    bindparam("financial_account_id", type_=PG_UUID(as_uuid=True)),
)


async def account_balances(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    as_of: date | None = None,
    financial_account_id: uuid.UUID | None = None,
) -> AccountBalances:
    resolved_as_of = as_of or date.today()
    result = await db.execute(
        _ACCOUNT_BALANCES_SQL,
        {
            "workspace_id": workspace_id,
            "as_of": resolved_as_of,
            "currency": currency,
            "financial_account_id": financial_account_id,
        },
    )
    accounts: list[AccountBalanceRow] = []
    liquidity_total = Decimal("0")
    debt_total = Decimal("0")
    for row in result.mappings().all():
        balance = Decimal(row["balance"])
        account_type = row["account_type"]
        if account_type in LIQUIDITY_ACCOUNT_TYPES:
            liquidity_total += balance
        elif account_type in DEBT_ACCOUNT_TYPES:
            debt_total += balance
        accounts.append(
            AccountBalanceRow(
                financial_account_id=row["financial_account_id"],
                name=row["name"],
                account_type=account_type,
                balance=balance,
            )
        )

    # M09b: valore REALE delle posizioni (prima sempre 0/False in M08, vedi
    # storia del commento su LIQUIDITY_ACCOUNT_TYPES). Import locale per
    # evitare un ciclo con `portfolio_analytics.py`, che chiama a sua volta
    # `account_balances` per lo snapshot patrimonio (vedi nota li').
    # NESSUN doppio conteggio: il saldo di un conto titoli e' sempre e solo
    # il cash su quel conto (LIQUIDITY_ACCOUNT_TYPES sopra); una posizione e'
    # un asset distinto, valorizzato qui separatamente — un acquisto reale
    # ha gia' ridotto il cash del conto (e quindi liquidity_total) tramite il
    # movimento bancario importato, prima ancora che la posizione esista.
    from app.services.portfolio_analytics import compute_valuation

    account_ids = {financial_account_id} if financial_account_id is not None else None
    valuation = await compute_valuation(db, workspace_id, account_ids, resolved_as_of, currency)

    return AccountBalances(
        accounts=accounts,
        liquidity_total=liquidity_total,
        debt_total=debt_total,
        investment_total=valuation.market_value,
        has_investments=valuation.has_holdings,
    )


async def _total_balance(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    as_of: date,
    financial_account_id: uuid.UUID | None,
) -> Decimal:
    """Saldo di riferimento per lo storico (`balance_history`): per un
    conto specifico e' il suo saldo; senza filtro e' la sola Liquidita' —
    non un "patrimonio totale" che mescolerebbe liquidita' e debiti
    (credit_card) in un unico numero senza che l'utente lo chieda
    esplicitamente (vedi breakdown per gruppo su `/net-worth`)."""
    balances = await account_balances(db, workspace_id, currency, as_of, financial_account_id)
    if financial_account_id is not None:
        return balances.accounts[0].balance if balances.accounts else Decimal("0")
    return balances.liquidity_total


def _bucket_expr(granularity: str):
    if granularity not in GRANULARITIES:
        raise ValueError(f"Granularita' non supportata: {granularity}")
    if granularity == "semester":
        # Postgres date_trunc() non conosce "semester" (unita' valide:
        # day/week/month/quarter/year/decade/century/millennium) — H1/H2
        # vanno costruiti a mano a partire dall'inizio dell'anno, mai un
        # remainder sul mese (deve combaciare esattamente con
        # analytics_calc._bucket_start/_next_bucket lato Python).
        year_start = func.date_trunc("year", cast(Transaction.transaction_date, SA_DateTime))
        return case(
            (func.extract("month", Transaction.transaction_date) <= 6, year_start),
            else_=year_start + text("interval '6 months'"),
        )
    return func.date_trunc(granularity, cast(Transaction.transaction_date, SA_DateTime))


async def balance_history(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    granularity: str,
    date_from: date,
    date_to: date,
    financial_account_id: uuid.UUID | None = None,
) -> list[dict]:
    current_total = await _total_balance(db, workspace_id, currency, date_to, financial_account_id)

    bucket_expr = _bucket_expr(granularity)
    query = (
        select(
            bucket_expr.label("bucket"),
            func.coalesce(func.sum(Transaction.amount), 0).label("delta"),
        )
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.currency == currency,
            Transaction.transaction_date >= date_from,
            Transaction.transaction_date <= date_to,
        )
        .group_by(bucket_expr)
    )
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)

    rows = (await db.execute(query)).all()
    deltas = {r.bucket.date(): Decimal(r.delta) for r in rows}
    buckets = generate_buckets(date_from, date_to, granularity)
    series = reconstruct_running_series(buckets, deltas, current_total)
    return [{"period": period, "balance": balance} for period, balance in series]


async def _income_expenses(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    date_from: date,
    date_to: date,
    financial_account_id: uuid.UUID | None,
) -> IncomeExpenses:
    query = select(
        func.coalesce(func.sum(func.greatest(Transaction.amount, 0)), 0).label("income"),
        func.coalesce(-func.sum(func.least(Transaction.amount, 0)), 0).label("expenses"),
    ).where(
        Transaction.workspace_id == workspace_id,
        Transaction.currency == currency,
        Transaction.transaction_type.notin_(_EXCLUDED_FROM_CASH_FLOW),
        Transaction.transaction_date >= date_from,
        Transaction.transaction_date <= date_to,
    )
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)
    row = (await db.execute(query)).one()
    return IncomeExpenses(income=Decimal(row.income), expenses=Decimal(row.expenses))


async def summary(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    date_from: date,
    date_to: date,
) -> dict:
    balances = await account_balances(db, workspace_id, currency, date_to)
    current = await _income_expenses(db, workspace_id, currency, date_from, date_to, None)
    prev_from, prev_to = previous_period(date_from, date_to)
    previous = await _income_expenses(db, workspace_id, currency, prev_from, prev_to, None)

    return {
        "currency": currency,
        "period": {"date_from": date_from, "date_to": date_to},
        "comparison_period": {"date_from": prev_from, "date_to": prev_to},
        "liquidity": balances.liquidity_total,
        "debt": balances.debt_total,
        "investments": balances.investment_total,
        # Rework dashboard interattivo: la nuova KPI "Patrimonio totale"
        # (SPEC.md §39/§73). Calcolato qui in Decimal, non lato frontend in
        # float, per lo stesso motivo per cui ogni altra somma di denaro in
        # questo modulo resta in Decimal fino alla serializzazione.
        # `debt_total` e' GIA' un saldo con segno (negativo quando si e' in
        # debito, vedi account_balances sopra) — si SOMMA cosi' com'e',
        # esattamente come in `portfolio_analytics._upsert_net_worth_snapshot`
        # (bug reale: la prima versione lo sottraeva di nuovo, raddoppiando
        # l'effetto e restituendo un patrimonio piu' alto in presenza di
        # debiti invece che piu' basso).
        "net_worth": balances.liquidity_total + balances.debt_total + balances.investment_total,
        "has_investments": balances.has_investments,
        "income": current.income,
        "expenses": current.expenses,
        "net_cash_flow": current.income - current.expenses,
        "previous_income": previous.income,
        "previous_expenses": previous.expenses,
        "previous_net_cash_flow": previous.income - previous.expenses,
    }


async def cash_flow(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    granularity: str,
    date_from: date,
    date_to: date,
    financial_account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
) -> list[dict]:
    bucket_expr = _bucket_expr(granularity)
    query = (
        select(
            bucket_expr.label("bucket"),
            func.coalesce(func.sum(func.greatest(Transaction.amount, 0)), 0).label("income"),
            func.coalesce(-func.sum(func.least(Transaction.amount, 0)), 0).label("expenses"),
        )
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.currency == currency,
            Transaction.transaction_type.notin_(_EXCLUDED_FROM_CASH_FLOW),
            Transaction.transaction_date >= date_from,
            Transaction.transaction_date <= date_to,
        )
        .group_by(bucket_expr)
    )
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)
    if category_id is not None:
        # Match padre-O-figlio, stesso pattern gia' usato in `by_merchant`
        # (il drill-down per il trend di una categoria del cruscotto: il
        # `category_id` qui e' spesso un group_id riaccorpato, le
        # transazioni sono taggate con la sottocategoria figlia).
        query = query.outerjoin(Category, Transaction.category_id == Category.id).where(
            or_(Transaction.category_id == category_id, Category.parent_id == category_id)
        )

    rows = (await db.execute(query)).all()
    by_bucket = {r.bucket.date(): (Decimal(r.income), Decimal(r.expenses)) for r in rows}
    buckets = generate_buckets(date_from, date_to, granularity)
    result = []
    for bucket in buckets:
        income, expenses = by_bucket.get(bucket, (Decimal("0"), Decimal("0")))
        result.append(
            {"period": bucket, "income": income, "expenses": expenses, "net": income - expenses}
        )
    return result


async def by_category(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    direction: str,
    date_from: date,
    date_to: date,
    financial_account_id: uuid.UUID | None = None,
) -> list[dict]:
    """Breakdown a DUE livelli (SPEC §22: le sottocategorie del seed non
    vanno oltre un livello): le transazioni di una sottocategoria vengono
    raggruppate sotto la categoria padre via `COALESCE(parent_id, id)`. Il
    drill-down per merchant dentro una categoria e' `by_merchant(...,
    category_id=...)` (SPEC_FE §30 raggruppa per merchant, non per
    sottocategoria)."""
    amount_filter = Transaction.amount < 0 if direction == "expense" else Transaction.amount > 0
    group_key = func.coalesce(Category.parent_id, Transaction.category_id)
    query = (
        select(
            group_key.label("group_id"),
            func.sum(func.abs(Transaction.amount)).label("total"),
            func.count().label("transactions_count"),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.currency == currency,
            Transaction.transaction_type.notin_(_EXCLUDED_FROM_CASH_FLOW),
            amount_filter,
            Transaction.transaction_date >= date_from,
            Transaction.transaction_date <= date_to,
        )
        .group_by(group_key)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
    )
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)

    rows = (await db.execute(query)).all()
    return await _label_category_rows(db, rows)


async def _label_category_rows(db: AsyncSession, rows) -> list[dict]:
    category_ids = [r.group_id for r in rows if r.group_id is not None]
    names: dict[uuid.UUID, str] = {}
    if category_ids:
        cat_rows = (
            await db.execute(select(Category.id, Category.name).where(Category.id.in_(category_ids)))
        ).all()
        names = {c.id: c.name for c in cat_rows}

    total_all = sum((Decimal(r.total) for r in rows), Decimal("0")) or Decimal("1")
    result = []
    for r in rows:
        total = Decimal(r.total)
        result.append(
            {
                "category_id": r.group_id,
                "name": names.get(r.group_id, "Senza categoria"),
                "total": total,
                "share": total / total_all,
                "transactions_count": r.transactions_count,
            }
        )
    return result


async def by_merchant(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    direction: str,
    date_from: date,
    date_to: date,
    financial_account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
) -> list[dict]:
    amount_filter = Transaction.amount < 0 if direction == "expense" else Transaction.amount > 0
    query = (
        select(
            Transaction.merchant,
            func.sum(func.abs(Transaction.amount)).label("total"),
            func.count().label("transactions_count"),
        )
        .where(
            Transaction.workspace_id == workspace_id,
            Transaction.currency == currency,
            Transaction.transaction_type.notin_(_EXCLUDED_FROM_CASH_FLOW),
            amount_filter,
            Transaction.transaction_date >= date_from,
            Transaction.transaction_date <= date_to,
        )
        .group_by(Transaction.merchant)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
    )
    if financial_account_id is not None:
        query = query.where(Transaction.financial_account_id == financial_account_id)
    if category_id is not None:
        # `category_id` qui e' quasi sempre il group_id RIACCORPATO di
        # `by_category` (COALESCE(parent_id, id)): puo' essere una
        # categoria padre, e le transazioni sono taggate con la
        # SOTTOCATEGORIA figlia, non col padre stesso. Un confronto diretto
        # `Transaction.category_id == category_id` non troverebbe mai nulla
        # per un padre con figli (bug osservato manualmente: drill-down su
        # "Alimentari" con transazioni su "Supermercato" → lista vuota).
        # Match quindi sulla categoria stessa O su una sua sottocategoria.
        query = query.outerjoin(Category, Transaction.category_id == Category.id).where(
            or_(Transaction.category_id == category_id, Category.parent_id == category_id)
        )

    rows = (await db.execute(query)).all()
    total_all = sum((Decimal(r.total) for r in rows), Decimal("0")) or Decimal("1")
    result = []
    for r in rows:
        total = Decimal(r.total)
        result.append(
            {
                "merchant": r.merchant or "Senza merchant",
                "total": total,
                "share": total / total_all,
                "transactions_count": r.transactions_count,
            }
        )
    return result

"""Lettura/scrittura dei tassi di cambio persistiti (SPEC sistema di
valute) — ponte tra `analytics.py`/`portfolio_analytics.py` e `fx_rates`.
Stesso principio architetturale di `AssetPrice`/`MarketDataProvider` (vedi
`app/marketdata/base.py`): chi valorizza un totale legge SEMPRE da qui, mai
direttamente da un provider — il fetch/persistenza vera avviene nel job
(`app/worker/jobs/market_data.py`) o via inserimento manuale.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import case, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.fx_rate import FxRate


async def get_rate(
    db: AsyncSession, from_currency: str, to_currency: str, as_of: date
) -> Decimal | None:
    """Ultimo tasso disponibile per la coppia richiesta, non piu' recente di
    `as_of` — mai il piu' recente in assoluto: un valore storico deve usare
    il tasso di QUELLA data, non quello di oggi (non ricostruibile a
    posteriori). `None` = nessun tasso persistito per questa coppia/periodo,
    il chiamante decide come degradare (mai un'eccezione: stesso principio
    di `_latest_price` in `portfolio_analytics.py`)."""
    if from_currency == to_currency:
        return Decimal("1")
    result = await db.execute(
        select(FxRate.rate)
        .where(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date <= as_of,
        )
        .order_by(FxRate.rate_date.desc())
        .limit(1)
    )
    rate = result.scalar_one_or_none()
    return rate


async def upsert_rate(
    db: AsyncSession, from_currency: str, to_currency: str, rate_date: date, rate: Decimal, source: str
) -> FxRate:
    """Upsert su `(from_currency, to_currency, rate_date)` — stesso principio
    di `AssetPrice`: un secondo fetch/inserimento per la stessa coppia/
    giorno sovrascrive, non duplica. Nessun `workspace_id`: la riga e'
    condivisa da tutti i workspace (vedi docstring di `FxRate`), quindi
    l'upsert non ha bisogno di isolamento RLS per la query di ricerca."""
    result = await db.execute(
        select(FxRate).where(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date == rate_date,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = FxRate(from_currency=from_currency, to_currency=to_currency, rate_date=rate_date)
        db.add(row)
    row.rate = rate
    row.source = source
    return row


def fx_rate_expr(currency_col: ColumnElement, date_col: ColumnElement, target_currency: str) -> ColumnElement:
    """Espressione SQL (non un valore Python) per il fattore di conversione
    verso `target_currency` — UNICO punto di conversione riusato in
    `analytics.py` in ogni SUM di aggregazione (`SUM(amount * fx_rate_expr
    (...))`), invece di un round-trip Python per riga come in
    `get_rate`/`portfolio_analytics.py` (li' i conteggi sono piccoli — poche
    posizioni — qui potenzialmente migliaia di transazioni: una subquery
    scalare correlata dentro la query stessa resta un'unica query, non N).

    `NULL` quando la valuta non e' quella target e nessun tasso e'
    disponibile per la data: `SUM(amount * NULL)` = NULL per quella riga,
    ignorato dall'aggregazione SQL — la riga resta onestamente esclusa dal
    totale (mai un errore), il chiamante verifica separatamente se questo e'
    successo con `has_unconverted_expr` (mai un'esclusione invisibile)."""
    rate_alias = aliased(FxRate)
    return case(
        (currency_col == target_currency, literal(Decimal("1"))),
        else_=(
            select(rate_alias.rate)
            .where(
                rate_alias.from_currency == currency_col,
                rate_alias.to_currency == target_currency,
                rate_alias.rate_date <= date_col,
            )
            .order_by(rate_alias.rate_date.desc())
            .limit(1)
            .correlate_except(rate_alias)
            .scalar_subquery()
        ),
    )


def has_unconverted_expr(currency_col: ColumnElement, date_col: ColumnElement, target_currency: str) -> ColumnElement:
    """True per una riga la cui valuta non e' `target_currency` e per cui
    nessun tasso e' disponibile — da aggregare con `bool_or(...)` per
    sapere se ALMENO una riga e' stata esclusa dal totale per questo
    motivo (`has_unconverted_rows` nella risposta API)."""
    return case(
        (currency_col == target_currency, literal(False)),
        else_=fx_rate_expr(currency_col, date_col, target_currency).is_(None),
    )

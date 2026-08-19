"""Test del servizio di lettura/scrittura tassi di cambio (sistema di
valute) — `fx_rates` non ha RLS (tabella globale, vedi `app/models/
fx_rate.py`), quindi nessun setup di workspace/identita' serve qui: un
`async_session_factory()` diretto basta, le valute di sistema (EUR/USD)
sono gia' seedate da `tests/conftest.py`.
"""
from datetime import date
from decimal import Decimal

from app.db.base import async_session_factory
from app.services.fx_rate_service import get_rate, upsert_rate


async def test_same_currency_returns_one_without_touching_db():
    async with async_session_factory() as db:
        rate = await get_rate(db, "EUR", "EUR", date(2026, 1, 1))
    assert rate == Decimal("1")


async def test_get_rate_returns_none_when_nothing_persisted():
    async with async_session_factory() as db:
        rate = await get_rate(db, "USD", "EUR", date(2026, 1, 1))
    assert rate is None


async def test_upsert_then_get_rate_roundtrip():
    async with async_session_factory() as db:
        await upsert_rate(db, "USD", "EUR", date(2026, 1, 15), Decimal("0.92"), "manual")
        await db.commit()

    async with async_session_factory() as db:
        rate = await get_rate(db, "USD", "EUR", date(2026, 1, 15))
    assert rate == Decimal("0.92")


async def test_get_rate_uses_the_latest_rate_not_newer_than_as_of():
    async with async_session_factory() as db:
        await upsert_rate(db, "USD", "EUR", date(2026, 1, 10), Decimal("0.90"), "manual")
        await upsert_rate(db, "USD", "EUR", date(2026, 1, 20), Decimal("0.95"), "manual")
        await db.commit()

    async with async_session_factory() as db:
        # Una data storica intermedia deve usare il tasso di QUELLA data
        # (10 gennaio), mai il piu' recente in assoluto (20 gennaio).
        rate = await get_rate(db, "USD", "EUR", date(2026, 1, 15))
    assert rate == Decimal("0.90")


async def test_upsert_same_pair_and_date_overwrites_not_duplicates():
    async with async_session_factory() as db:
        await upsert_rate(db, "USD", "EUR", date(2026, 2, 1), Decimal("0.91"), "manual")
        await db.commit()
    async with async_session_factory() as db:
        await upsert_rate(db, "USD", "EUR", date(2026, 2, 1), Decimal("0.93"), "yahoo")
        await db.commit()

    async with async_session_factory() as db:
        rate = await get_rate(db, "USD", "EUR", date(2026, 2, 1))
    assert rate == Decimal("0.93")


async def test_get_rate_does_not_assume_symmetry():
    # Un tasso EUR->USD non implica una riga USD->EUR — nessuna deduzione
    # 1/rate, mai persistita ne' letta automaticamente.
    async with async_session_factory() as db:
        await upsert_rate(db, "EUR", "USD", date(2026, 3, 1), Decimal("1.08"), "manual")
        await db.commit()

    async with async_session_factory() as db:
        rate = await get_rate(db, "USD", "EUR", date(2026, 3, 1))
    assert rate is None

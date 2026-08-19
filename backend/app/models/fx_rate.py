import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Stesso enum di ASSET_PRICE_SOURCES (asset_price.py): "manual" per un tasso
# inserito a mano, le altre per un fetch riuscito dal market data provider
# attivo di UN workspace — ma il tasso stesso e' condiviso da tutti (vedi
# docstring di classe).
FX_RATE_SOURCES = ("manual", "stooq", "yahoo", "custom")


class FxRate(Base):
    """Storico dei tassi di cambio (SPEC sistema di valute) — a differenza
    di `AssetPrice` (legata a un asset di UN workspace), questa tabella e'
    GLOBALE: nessun `workspace_id`, nessuna Row-Level Security. Un tasso
    EUR/USD del 15 marzo e' un fatto di mercato oggettivo, non un dato di
    tenant — una singola riga scaricata (dal profilo market data attivo di
    QUALUNQUE workspace che ne ha bisogno) beneficia tutti gli altri, senza
    fetch ridondanti dello stesso dato pubblico. Upsert su
    `(from_currency, to_currency, rate_date)`: un secondo fetch/inserimento
    per la stessa coppia/giorno sovrascrive, non duplica (stesso principio
    di `AssetPrice`).

    Nessuna riga inversa calcolata automaticamente: un tasso EUR->USD non
    implica una riga USD->EUR (il tasso scaricato non e' garantito
    simmetrico a 1/rate) — chi ha bisogno della direzione inversa la cerca
    esplicitamente, mai dedotta.
    """

    __tablename__ = "fx_rates"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'stooq', 'yahoo', 'custom')", name="ck_fx_rates_source"
        ),
        UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_rates_pair_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    from_currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code"), nullable=False, index=True
    )
    to_currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code"), nullable=False, index=True
    )
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

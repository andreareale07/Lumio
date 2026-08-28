import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# "none" non e' un valore persistibile (come per AI_PROVIDERS): l'assenza di
# un profilo attivo E' lo stato disabilitato (SPEC §38), vedi registry.py.
MARKET_DATA_PROVIDERS = ("manual", "stooq", "yahoo", "custom")


class MarketDataProfile(Base):
    """Milestone 09b — configurazione MarketDataProvider per workspace
    (SPEC §38). Stesso pattern di `AIProfile` (M07): piu' profili per
    workspace, al massimo UNO con `is_active=true`
    (`uq_market_data_profiles_one_active_per_workspace`, indice UNIQUE
    parziale — mutua esclusivita' a livello DB). Nessun profilo attivo =
    market data disabilitato per il workspace: le posizioni restano
    valorizzate a costo storico, mai un crash (DoD M09).

    `provider` e' immutabile dopo la creazione, stesso motivo di `AIProfile`:
    cambiare provider significa creare un nuovo profilo.

    `price_field`/`currency_field` sono percorsi puntati nella risposta JSON
    (es. "quote.price") usati SOLO da `provider='custom'` — ignorati dagli
    altri provider, che sanno gia' come interpretare la propria risposta.

    `portfolio_refresh_interval_seconds`/`detail_refresh_interval_seconds`
    (docs/SPEC_STOCK_PRICE.md): intervallo MINIMO tra due chiamate reali al
    provider, non un TTL esatto del valore mostrato. Il primo governa la
    cadenza con cui il job bulk (posizioni aperte) puo' essere ri-triggerato
    in background mentre l'utente naviga le viste portfolio-wide
    (`app/worker/jobs/market_data.py`); il secondo la cadenza minima di
    fetch per la live-quote di un singolo asset (`app/services/
    live_quote_service.py`), il cui TTL Redis e' leggermente maggiore
    (+5s) per evitare la race alla scadenza esatta.
    """

    __tablename__ = "market_data_profiles"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "provider IN ('manual', 'stooq', 'yahoo', 'custom')",
            name="ck_market_data_profiles_provider",
        ),
        CheckConstraint(
            "portfolio_refresh_interval_seconds BETWEEN 300 AND 86400",
            name="ck_market_data_profiles_portfolio_refresh_interval",
        ),
        CheckConstraint(
            "detail_refresh_interval_seconds BETWEEN 5 AND 3600",
            name="ck_market_data_profiles_detail_refresh_interval",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    price_field: Mapped[str | None] = mapped_column(String, nullable=True)
    currency_field: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    portfolio_refresh_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("900")
    )
    detail_refresh_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("15")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

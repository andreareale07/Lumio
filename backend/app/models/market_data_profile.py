import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func, text
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
    """

    __tablename__ = "market_data_profiles"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "provider IN ('manual', 'stooq', 'yahoo', 'custom')",
            name="ck_market_data_profiles_provider",
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

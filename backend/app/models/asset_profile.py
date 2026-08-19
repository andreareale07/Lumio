import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKeyConstraint, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetProfile(Base):
    """Arricchimento best-effort di un asset (Step 3 pagina dettaglio:
    emittente, categoria, patrimonio del fondo, accumulo/distribuzione) —
    SEMPRE opzionale, ogni campo puo' essere `NULL` (dato non disponibile
    dal provider, mai un errore). `fetched_at` e' la cache: i dati di un
    fondo cambiano di rado, quindi si rifa' un fetch solo se piu' vecchio di
    ~30 giorni (vedi `app/services/asset_profile_service.py`), non a ogni
    apertura della pagina."""

    __tablename__ = "asset_profiles"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("workspace_id", "asset_id", name="uq_asset_profiles_asset"),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_profiles_workspace_asset",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    issuer: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    aum: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    distribution_policy: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nome "pulito" secondo il provider (es. "Apple Inc.") — MAI usato per
    # sovrascrivere `Asset.name` (che resta il nome grezzo estratto dal
    # parser, spesso con suffissi di borsa tedeschi tipo "DL-,0001" = valore
    # nominale in dollari): solo un'alternativa opzionale che il chiamante
    # sceglie se e dove mostrare al posto di quello grezzo.
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

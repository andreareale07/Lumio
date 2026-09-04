import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetTaxClassification(Base):
    """Override utente della classe fiscale derivata di un asset
    (SPEC_TAX_REGIME.md FETTA 1). Riga presente SOLO se l'utente sovrascrive
    il default derivato da `TaxJurisdiction.derive_asset_class` — l'assenza
    di riga significa "usa il derivato", mai "not_codified di default".

    Non su `assets` (concetto giurisdizione-specifico in un catalogo
    neutro) ne' su `asset_profiles` (cache con TTL 30gg che si rigenera,
    perderebbe l'override)."""

    __tablename__ = "asset_tax_classifications"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_tax_classifications_workspace_asset",
        ),
        UniqueConstraint(
            "workspace_id", "asset_id", "jurisdiction_code", name="uq_asset_tax_classifications_asset_jurisdiction"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    jurisdiction_code: Mapped[str] = mapped_column(String, nullable=False)
    asset_class: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

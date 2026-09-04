import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkspaceTaxResidence(Base):
    """Residenza fiscale del workspace, APPEND-ONLY per anno di decorrenza —
    stesso pattern minimo di [[FinancialAccountTaxRegime]] (nessun
    `valid_from`/`valid_to`: l'intervallo di una riga e' `[fiscal_year,
    next.fiscal_year)`, risolto a lettura ordinando per `fiscal_year`,
    vedi `tax_context.resolve_tax_context`). L'utente imposta la residenza
    UNA VOLTA e resta valida finche' non la cambia, non deve ridichiararla
    ogni anno. Granularita' ANNO (non una data esatta) perche' l'Italia non
    ha split-year: si e' residenti per l'intero anno solare, mai per una
    frazione — un cambio di residenza a meta' anno si registra comunque
    con l'anno intero in cui e' avvenuto. Storico multi-periodo supportato
    aggiungendo piu' righe (es. 2010 IT, 2015 CH, 2020 IT).
    `jurisdiction_code` risolve quale `TaxJurisdiction`
    (`app/tax/registry.py`) applicare."""

    __tablename__ = "workspace_tax_residences"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("workspace_id", "fiscal_year", name="uq_workspace_tax_residences_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    jurisdiction_code: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

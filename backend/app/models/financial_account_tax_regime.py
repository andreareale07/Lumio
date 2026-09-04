import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKeyConstraint, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancialAccountTaxRegime(Base):
    """Periodo di regime fiscale di un conto (SPEC_TAX_REGIME.md FETTA 1) —
    caso canonico: un conto Trade Republic nato in regime dichiarativo
    (IBAN tedesco, nessuna stabile organizzazione italiana) e passato ad
    amministrato quando TR ha attivato l'IBAN italiano.

    APPEND-ONLY, niente `valid_to` (stesso pattern minimo di
    [[FinancialAccountIbanHistory]], qui esteso con un intervallo):
    l'intervallo di una riga e' `[effective_from, next.effective_from)`,
    risolto a lettura ordinando per `effective_from`
    (`tax_regime_service.resolve_regime_at`). Sovrapposizioni impossibili
    per costruzione — nessun `EXCLUDE`/`btree_gist` necessario.
    `regime_code` non ha un CHECK enum: e' vocabolario della giurisdizione
    (`jurisdiction.regimes(effective_from)`), validato al confine
    applicativo, mai in DB."""

    __tablename__ = "financial_account_tax_regimes"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_financial_account_tax_regimes_workspace_account",
        ),
        UniqueConstraint(
            "workspace_id",
            "financial_account_id",
            "effective_from",
            name="uq_financial_account_tax_regimes_effective_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    regime_code: Mapped[str] = mapped_column(String, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

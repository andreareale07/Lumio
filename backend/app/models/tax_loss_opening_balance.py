import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKeyConstraint, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaxLossOpeningBalance(Base):
    """Saldo di apertura dello zainetto fiscale, inserito a mano
    (SPEC_TAX_REGIME.md FETTA 1) — in questa fetta e' l'UNICA fonte che
    alimenta `build_loss_pocket` (`app/services/tax_calc.py`): lo storico
    dell'utente in Lumio copre solo una piccola parte del periodo reale,
    i lotti anteriori non sono ricostruibili.

    `financial_account_id` NULL = perimetro dichiarativo aggregato
    (personale, su tutti i conti); valorizzato = perimetro amministrato
    per quell'intermediario. Il vincolo "regime dichiarativo <->
    financial_account_id NULL" non e' esprimibile in DB (dipende dal
    `pocket_scope` del regime, dato in codice) — enforced in
    `tax_opening_service.py` con 400 esplicito.

    `amount` e' il NOMINALE, mai convertito: la conversione (DL 66/2014)
    si applica a lettura in `tax_calc.build_loss_pocket`, mai qui.
    `formed_under_ruleset_code` e' un timbro di audit scritto dal SERVER
    risolvendo `formation_date` — mai dal client."""

    __tablename__ = "tax_loss_opening_balances"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_tax_loss_opening_balances_workspace_account",
        ),
        # Due indici UNIQUE parziali (mai un solo UniqueConstraint: NULL non
        # e' mai uguale a NULL, quindi non basterebbe da solo a impedire
        # duplicati nel perimetro dichiarativo, dove financial_account_id
        # e' sempre NULL) — uno per perimetro, mai sovrapposti per
        # costruzione (`postgresql_where` si escludono a vicenda).
        Index(
            "uq_tax_loss_opening_balances_per_account",
            "workspace_id",
            "financial_account_id",
            "formation_date",
            unique=True,
            postgresql_where=text("financial_account_id IS NOT NULL"),
        ),
        Index(
            "uq_tax_loss_opening_balances_aggregate",
            "workspace_id",
            "formation_date",
            unique=True,
            postgresql_where=text("financial_account_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    formation_date: Mapped[date] = mapped_column(Date, nullable=False)
    formed_under_ruleset_code: Mapped[str] = mapped_column(String, nullable=False)
    income_category: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

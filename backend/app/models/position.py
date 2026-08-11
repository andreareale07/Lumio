import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKeyConstraint, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Position(Base):
    """Milestone 09 — quantita' posseduta per (conto, asset) (SPEC §34).

    Materializzata ma SEMPRE derivata dai movimenti di
    `investment_transactions` — mai una seconda fonte di verita' indipendente.
    Il ricalcolo e' idempotente e integrale (rilegge tutti i movimenti),
    vedi `app/services/position_service.py:recompute_position` e la
    matematica pura in `app/services/position_calc.py`.

    Si lega a `financial_account_id`, MAI all'`account_type` del conto
    (decisione M08 confermata con l'utente: un conto "checking" puo' avere
    posizioni reali, es. un PAC su un conto Trade Republic usato anche per
    la spesa quotidiana).
    """

    __tablename__ = "positions"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "financial_account_id", "asset_id", name="uq_positions_account_asset"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_positions_workspace_account",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_positions_workspace_asset",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False, server_default=text("0"))
    average_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, server_default=text("0")
    )
    realized_pl: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

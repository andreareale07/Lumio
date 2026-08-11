import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# SPEC §35 elenca 8 tipi. Due estensioni documentate (decisione presa in
# fase di analisi M09, non specificata dalla SPEC):
# - "opening": carico di una posizione preesistente (onboarding senza dover
#   inserire anni di storico), non un acquisto del periodo.
# - "adjustment": riconciliazione generata quando l'utente modifica una
#   posizione a mano (vedi `app/services/position_service.py`) — mantiene
#   `investment_transactions` come UNICA sorgente di verita', mai una
#   posizione editabile in modo indipendente dal libro mastro.
INVESTMENT_TRANSACTION_TYPES = (
    "buy",
    "sell",
    "dividend",
    "deposit",
    "withdrawal",
    "fee",
    "tax",
    "split",
    "opening",
    "adjustment",
)


class InvestmentTransaction(Base):
    """Milestone 09 — libro mastro degli investimenti (SPEC §35).

    Unica sorgente di verita' per le posizioni: `positions` e' sempre
    derivata da qui (`app/services/position_service.py:recompute_position`),
    mai un secondo modello indipendente da riconciliare.

    `asset_id` e' nullable: `deposit`/`withdrawal`/`fee` possono essere puri
    movimenti di cassa sul conto titoli, senza riferirsi a uno strumento.

    `transaction_id` e' un link OPZIONALE e MANUALE verso la transazione
    bancaria corrispondente (mai creato automaticamente): il cash di un
    acquisto scende gia' dall'estratto conto importato in `transactions`,
    quindi generare qui una seconda scrittura duplicherebbe il movimento.
    `ondelete="SET NULL"`: cancellare la transazione bancaria non deve mai
    cancellare lo storico investimenti, solo scollegarlo.

    `source_type_raw` esiste fin da subito (stesso campo di
    `Transaction.source_type_raw`, hotfix pre-M09) cosi' un futuro parser
    che alimenti questo dominio non perde il dato grezzo del provider.
    """

    __tablename__ = "investment_transactions"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "type IN ('buy', 'sell', 'dividend', 'deposit', 'withdrawal', "
            "'fee', 'tax', 'split', 'opening', 'adjustment')",
            name="ck_investment_transactions_type",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_investment_transactions_workspace_account",
        ),
        # asset_id nullable: una FK composita con colonna NULL e' comunque
        # satisfied (MATCH SIMPLE, default Postgres) senza bisogno di trigger.
        ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="RESTRICT",
            name="fk_investment_transactions_workspace_asset",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="SET NULL",
            name="fk_investment_transactions_workspace_transaction",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_investment_transactions_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    financial_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    # Impatto netto in cassa del movimento, con segno (negativo = esce cash
    # dal conto, come per `Transaction.amount`). Per dividend/fee/tax e' il
    # solo importo, senza quantity/price.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default=text("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source_type_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

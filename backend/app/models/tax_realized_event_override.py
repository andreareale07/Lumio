import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaxRealizedEventOverride(Base):
    """Override utente di un evento realizzato specifico (FETTA 2 —
    `app/services/tax_lot_calc.py`/`tax_realized_service.py`). Riga presente
    SOLO se l'utente corregge il calcolo automatico (es. un costo di carico
    storico sbagliato prima che iniziasse a usare Lumio) — l'assenza di riga
    significa "usa il valore calcolato", stesso principio gia' scelto per
    `AssetTaxClassification`.

    Un evento realizzato e' identificato dalla coppia
    `(lot_transaction_id, sell_transaction_id)` — MAI una sola data: piu'
    movimenti nello stesso giorno la renderebbero ambigua, e una singola
    vendita puo' consumare piu' lotti (piu' eventi con lo stesso
    `sell_transaction_id`). Questa coppia e' univoca per costruzione: il
    motore a lotti consuma un dato lotto al massimo una volta per vendita
    (vedi `tax_lot_calc.compute_tax_lots`).

    `override_gain_or_loss` sostituisce il gain/loss CALCOLATO per la sola
    classificazione fiscale (zainetto/compensazione) — non tocca
    `investment_transactions` ne' la scomposizione aperto/chiuso mostrata
    nel dettaglio asset (portfolio), che restano il dato oggettivo. `excluded`
    forza l'esclusione dal calcolo indipendentemente dalla classificazione
    automatica — un quarto motivo di esclusione (`user_excluded`) accanto ai
    tre gia' esistenti (asset non codificato/nessun regime/trattamento non
    codificato)."""

    __tablename__ = "tax_realized_event_overrides"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "lot_transaction_id"],
            ["investment_transactions.workspace_id", "investment_transactions.id"],
            ondelete="CASCADE",
            name="fk_tax_realized_event_overrides_workspace_lot_transaction",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "sell_transaction_id"],
            ["investment_transactions.workspace_id", "investment_transactions.id"],
            ondelete="CASCADE",
            name="fk_tax_realized_event_overrides_workspace_sell_transaction",
        ),
        UniqueConstraint(
            "workspace_id",
            "lot_transaction_id",
            "sell_transaction_id",
            name="uq_tax_realized_event_overrides_event",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    lot_transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sell_transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    override_gain_or_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Currency(Base):
    """Sistema di valute (SPEC "tabella di sistema, non piu' un codice a 3
    lettere libero") — stesso pattern di `Category` per una tabella
    condivisa fra workspace (`workspace_id` nullable = riga di sistema,
    visibile a tutti via RLS), ma con una differenza deliberata: qui
    `code` E' la chiave primaria, globalmente univoca. Un codice valuta
    (ISO-4217 o non, es. "BTC") ha gia' un significato universale — a
    differenza del `code` di una categoria (nome scelto liberamente
    dall'utente), non serve la coppia `(workspace_id, code)` ne' il trigger
    anti-shadowing di `categories` (migration 0021): una `Currency` custom
    di un workspace occupa comunque un codice mai riusato da nessun altro,
    la PRIMARY KEY lo garantisce da sola. Le FK dal dominio (`Asset.
    currency`, `FinancialAccount.currency`, `Workspace.base_currency`)
    puntano direttamente a `currencies.code`, non a un id sintetico — le
    colonne esistenti sono gia' `String(3)` col valore giusto, nessuna
    migrazione dei dati esistenti necessaria oltre al vincolo FK.
    """

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    # Cifre decimali convenzionali per questa valuta (2 per EUR/USD, 0 per
    # JPY) — solo un suggerimento di formattazione per il frontend, mai
    # applicato agli arrotondamenti finanziari interni (sempre 2 decimali
    # per coerenza con `Numeric(18,2)` gia' in uso ovunque nel dominio).
    decimal_digits: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

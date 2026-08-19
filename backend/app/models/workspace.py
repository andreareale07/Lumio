import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Valuta di riferimento per i totali aggregati (patrimonio, portafoglio,
    # entrate/uscite) — impostazione ESPLICITA (sistema di valute, sostituisce
    # l'euristica "valuta prevalente tra i conti" di analytics.resolve_currency).
    # Cambiarla non riconverte nulla di storico: e' solo la valuta in cui i
    # totali vengono calcolati da quel momento, i dati grezzi restano sempre
    # nella loro valuta originale (vedi app/services/analytics.py).
    base_currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code"), nullable=False, server_default=text("'EUR'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

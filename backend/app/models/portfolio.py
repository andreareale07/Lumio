import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Portfolio(Base):
    """Milestone 09 — vista aggregata su piu' conti (SPEC §36).

    "Tutti i conti" (vista aggregata senza filtro) resta implicita nella UI,
    non una riga in questa tabella: un portfolio esiste solo quando l'utente
    vuole raggruppare un sottoinsieme specifico di conti sotto un nome.
    """

    __tablename__ = "portfolios"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_portfolios_workspace_name"),
        # Abilita la FK composita da `portfolio_accounts`.
        UniqueConstraint("workspace_id", "id", name="uq_portfolios_workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BankParser(Base):
    """SPEC §17: `bank_parsers` separa la banca dal parser/versione che la
    interpreta ("Trade Republic -> parser v1, parser v2"). Entita' globale
    come `banks` (nessuna RLS): il parser concreto (codice) vive nel registro
    di `app/parsers/__init__.py`, questa tabella traccia solo QUALE
    banca/versione un import ha effettivamente usato (audit) e permette di
    disattivare una versione (`is_active`) senza cancellarla — la gestione
    dinamica non e' nello scope di M05, le righe sono seedate dalla
    migration, stesso pattern di `banks`.
    """

    __tablename__ = "bank_parsers"
    __table_args__ = (
        UniqueConstraint("bank_id", "parser_type", "version", name="uq_bank_parsers_bank_type_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    bank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("banks.id"), nullable=False)
    parser_type: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

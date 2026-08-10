import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CLASSIFICATION_METHODS = ("rule", "ai", "user", "manual", "system")


class Classification(Base):
    """Milestone 06 — storico separato dalla transazione (SPEC §24), append-only
    (nessuna policy RLS UPDATE/DELETE, vedi migration 0006: con FORCE ROW
    LEVEL SECURITY questo nega di default le due operazioni per `lumio_app`,
    stesso pattern gia' usato per le system category in `0003`).

    Solo `rule`/`manual`/`user` sono scritti in M06: `ai`/`system` restano
    riservati a milestone future (M07+). Niente `subcategory_id` (presente
    nello schema SPEC ma ridondante con la gerarchia gia' costruita in M03
    via `categories.parent_id` — `category_id` punta gia' al nodo scelto,
    foglia o meno). `created_by_user_id` non e' nello schema SPEC ma e'
    necessario per il DoD ("chi ha classificato"): stesso precedente gia'
    accettato in M04 con `imports.created_by_user_id`. Valorizzato solo per
    `method IN ('user', 'manual')`.
    """

    __tablename__ = "classifications"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(
            "method IN ('rule', 'ai', 'user', 'manual', 'system')", name="ck_classifications_method"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    explanation: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

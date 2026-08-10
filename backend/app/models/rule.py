import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RULE_FIELDS = ("description", "merchant")
RULE_OPERATORS = ("equals", "contains", "starts_with", "ends_with", "regex", "merchant_equals")


class Rule(Base):
    """Milestone 06 — regola deterministica valutata prima di qualsiasi AI
    (SPEC §23). `field` seleziona il testo da confrontare: `description`
    legge `description_normalized` con fallback su `description_raw`,
    `merchant` legge `transactions.merchant` (oggi sempre NULL, nessun
    parser lo popola ancora). `category_id` NOT NULL: una regola senza
    categoria bersaglio non ha senso. FK semplice (non composita) verso
    `categories.id` perche' puo' puntare anche a una categoria di sistema
    (workspace_id NULL) — l'isolamento cross-tenant e' garantito dal trigger
    `check_transaction_category_workspace` (riusato da `transactions`,
    vedi migration 0006), non da RLS+FK.
    """

    __tablename__ = "rules"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("field IN ('description', 'merchant')", name="ck_rules_field"),
        CheckConstraint(
            "operator IN ('equals', 'contains', 'starts_with', 'ends_with', 'regex', 'merchant_equals')",
            name="ck_rules_operator",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

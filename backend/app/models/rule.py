import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RULE_FIELDS = ("description", "merchant")
RULE_OPERATORS = ("equals", "contains", "starts_with", "ends_with", "regex", "merchant_equals")
RULE_MATCH_MODES = ("all", "any")


class Rule(Base):
    """Milestone 06 — regola deterministica valutata prima di qualsiasi AI
    (SPEC §23). `conditions` e' una lista JSON (1..10) di condizioni di testo
    (`field` description/merchant + `operator` + `value`) o sull'importo
    (`field='amount'`, `operator='between'`, `min`/`max` come stringhe
    decimali), combinate da `match_mode` ('all' = E, 'any' = O). Il campo
    `description` legge `description_normalized` con fallback su
    `description_raw`, `merchant` legge `transactions.merchant`. Le
    condizioni vivono in JSONB e non in una tabella figlia: una regola si
    legge e si scrive sempre per intero, mai per singola condizione.
    `category_id` NOT NULL: una regola senza
    categoria bersaglio non ha senso. FK semplice (non composita) verso
    `categories.id` perche' puo' puntare anche a una categoria di sistema
    (workspace_id NULL) — l'isolamento cross-tenant e' garantito dal trigger
    `check_transaction_category_workspace` (riusato da `transactions`,
    vedi migration 0006), non da RLS+FK.
    """

    __tablename__ = "rules"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("match_mode IN ('all', 'any')", name="ck_rules_match_mode"),
        CheckConstraint(
            "jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) BETWEEN 1 AND 10",
            name="ck_rules_conditions",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    conditions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    match_mode: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'all'"))
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

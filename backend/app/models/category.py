import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Rework tassonomia (migration 0021/0022, vedi app/classification/taxonomy.py).
# VARCHAR + CHECK invece di un enum PG, per coerenza con transaction_type/
# direction/method/operator (tutti VARCHAR+CHECK altrove nel dominio) e per
# poter estendere l'insieme di valori con una migration ordinaria (un enum PG
# richiederebbe ALTER TYPE ... ADD VALUE, non transazionale).
CATEGORY_KINDS = ("expense", "income", "transfer", "investment", "neutral")


class Category(Base):
    __tablename__ = "categories"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("kind IN ('expense', 'income', 'transfer', 'investment', 'neutral')", name="ck_categories_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    # Ereditato dal padre, mai scelto liberamente su un figlio: imposto sia in
    # applicazione (app/services/category_service.py) sia a livello DB dal
    # trigger enforce_category_kind (migration 0021) — un INSERT/UPDATE che
    # aggirasse l'API non puo' comunque produrre un figlio con kind diverso
    # dal padre. Su un cambio di kind di una radice, cascade_category_kind
    # propaga il nuovo valore a tutti i figli.
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'expense'"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PUSH_PLATFORMS = ("android", "ios")


class PushDevice(Base):
    """Dispositivo mobile registrato per le notifiche push (token FCM).

    RLS owner-only: i dispositivi di un utente non li vede nessun altro membro
    del workspace. Il token identifica il telefono presso FCM ma da solo non
    consente di leggere dati; si elimina quando FCM lo dichiara non piu' valido.
    """

    __tablename__ = "push_devices"
    __table_args__ = (
        CheckConstraint("platform IN ('android', 'ios')", name="ck_push_devices_platform"),
        UniqueConstraint("owner_user_id", "token", name="uq_push_devices_owner_token"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

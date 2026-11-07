"""push_devices: dispositivi mobili registrati per le notifiche push

Revision ID: 0046_push_devices
Revises: 0045_totp_2fa
Create Date: 2026-11-07

Un record per dispositivo (token FCM dell'app Android). RLS FORCE con 4 policy,
OWNER-ONLY come le connessioni bancarie: le notifiche parlano dei movimenti di un
utente, nessun altro membro del workspace deve vedere i suoi dispositivi.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_push_devices"
down_revision: Union[str, None] = "0045_totp_2fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OWNER = (
    "owner_user_id = current_setting('app.current_user_id', true)::uuid "
    "AND is_workspace_member(workspace_id)"
)


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String, nullable=False),
        sa.Column("token", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("platform IN ('android', 'ios')", name="ck_push_devices_platform"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_user_id", "token", name="uq_push_devices_owner_token"),
    )
    op.create_index("ix_push_devices_workspace_id", "push_devices", ["workspace_id"])
    op.execute("ALTER TABLE push_devices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE push_devices FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY push_devices_select ON push_devices FOR SELECT USING ({_OWNER})")
    op.execute(f"CREATE POLICY push_devices_insert ON push_devices FOR INSERT WITH CHECK ({_OWNER})")
    op.execute(
        f"CREATE POLICY push_devices_update ON push_devices FOR UPDATE USING ({_OWNER}) WITH CHECK ({_OWNER})"
    )
    op.execute(f"CREATE POLICY push_devices_delete ON push_devices FOR DELETE USING ({_OWNER})")


def downgrade() -> None:
    for policy in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS push_devices_{policy} ON push_devices")
    op.drop_index("ix_push_devices_workspace_id", table_name="push_devices")
    op.drop_table("push_devices")

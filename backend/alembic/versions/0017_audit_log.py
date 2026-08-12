"""audit_log + RLS (append-only)

Revision ID: 0017_audit_log
Revises: 0016_google_integrations
Create Date: 2026-08-12

Milestone 11 — Hardening (SPEC §59): registro delle azioni rilevanti
(LOGIN, IMPORT_CREATED, ecc.). A differenza di ogni altra tabella RLS del
progetto, qui esistono SOLO le policy SELECT/INSERT — nessuna UPDATE/DELETE,
per design: un log di audit non deve essere alterabile nemmeno da un membro
del workspace stesso.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017_audit_log"
down_revision: Union[str, None] = "0016_google_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EVENT_TYPES = (
    "LOGIN",
    "IMPORT_CREATED",
    "IMPORT_COMPLETED",
    "TRANSACTION_UPDATED",
    "CATEGORY_CHANGED",
    "RULE_CREATED",
    "RULE_UPDATED",
    "AI_PROVIDER_CHANGED",
    "GOOGLE_CONNECTED",
    "EXPORT_CREATED",
)


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("entity_type", sa.String, nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "event_type IN (" + ", ".join(f"'{e}'" for e in _EVENT_TYPES) + ")",
            name="ck_audit_log_event_type",
        ),
    )
    op.create_index("ix_audit_log_workspace_id", "audit_log", ["workspace_id"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY audit_log_select ON audit_log FOR SELECT "
        "USING (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY audit_log_insert ON audit_log FOR INSERT "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_insert ON audit_log")
    op.execute("DROP POLICY IF EXISTS audit_log_select ON audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_workspace_id", table_name="audit_log")
    op.drop_table("audit_log")

"""ai_run_events: registro persistente di esecuzioni ed errori del motore AI

Revision ID: 0042_ai_run_events
Revises: 0041_positions_recompute_job
Create Date: 2026-10-24

Il motore AI di classificazione lasciava traccia di errori e motivi di
mancata esecuzione (provider spento, nessun profilo attivo, job interrotto)
solo nel log del worker, che l'utente non vede. Questa tabella li rende
consultabili in Impostazioni > Motore AI. Workspace-scoped con RLS, stesso
schema di `detection_overrides` (select/insert/delete; nessun update: e' un
registro append-only).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042_ai_run_events"
down_revision: Union[str, None] = "0041_positions_recompute_job"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_run_events",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_kind", sa.String, nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("message", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "run_kind IN ('import_classification', 'reclassification')", name="ck_ai_run_events_run_kind"
        ),
        sa.CheckConstraint("severity IN ('error', 'warning', 'info')", name="ck_ai_run_events_severity"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "import_id"],
            ["imports.workspace_id", "imports.id"],
            ondelete="CASCADE",
            name="fk_ai_run_events_workspace_import",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ai_run_events_workspace_created", "ai_run_events", ["workspace_id", "created_at"])

    op.execute("ALTER TABLE ai_run_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_run_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ai_run_events_select ON ai_run_events FOR SELECT USING (is_workspace_member(workspace_id))"
    )
    op.execute(
        "CREATE POLICY ai_run_events_insert ON ai_run_events FOR INSERT "
        "WITH CHECK (is_workspace_member(workspace_id))"
    )
    op.execute(
        "CREATE POLICY ai_run_events_delete ON ai_run_events FOR DELETE USING (is_workspace_member(workspace_id))"
    )


def downgrade() -> None:
    for policy in ("select", "insert", "delete"):
        op.execute(f"DROP POLICY IF EXISTS ai_run_events_{policy} ON ai_run_events")
    op.drop_table("ai_run_events")

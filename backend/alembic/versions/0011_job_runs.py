"""job_runs + RLS

Revision ID: 0011_job_runs
Revises: 0010_market_data
Create Date: 2026-08-11

Gap UX emerso testando M09b: il refresh prezzi e il ricalcolo snapshot
mostravano solo un toast effimero, nessuna traccia dopo un refresh pagina
(l'utente non sa se/quando l'ultima esecuzione e' riuscita). Questa tabella
e' lo stato minimo persistente, una sola riga per (workspace, job_kind),
sovrascritta a ogni esecuzione — non uno storico completo, che qui non
serve (vedi docstring di `app/models/job_run.py`).

Stesso pattern RLS standard di `0003`/`0007`/`0009`/`0010`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_job_runs"
down_revision: Union[str, None] = "0010_market_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_kind", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("job_id", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message", sa.String, nullable=True),
        sa.CheckConstraint(
            "job_kind IN ('market_data_refresh', 'snapshot_rebuild')", name="ck_job_runs_job_kind"
        ),
        sa.CheckConstraint("status IN ('running', 'success', 'failed')", name="ck_job_runs_status"),
        sa.UniqueConstraint("workspace_id", "job_kind", name="uq_job_runs_workspace_kind"),
    )
    op.create_index("ix_job_runs_workspace_id", "job_runs", ["workspace_id"])

    op.execute("ALTER TABLE job_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY job_runs_select ON job_runs FOR SELECT "
        "USING (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY job_runs_insert ON job_runs FOR INSERT "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY job_runs_update ON job_runs FOR UPDATE "
        "USING (is_workspace_member(workspace_id)) "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY job_runs_delete ON job_runs FOR DELETE "
        "USING (is_workspace_member(workspace_id));"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS job_runs_delete ON job_runs")
    op.execute("DROP POLICY IF EXISTS job_runs_update ON job_runs")
    op.execute("DROP POLICY IF EXISTS job_runs_insert ON job_runs")
    op.execute("DROP POLICY IF EXISTS job_runs_select ON job_runs")
    op.drop_index("ix_job_runs_workspace_id", table_name="job_runs")
    op.drop_table("job_runs")

"""google_integrations + RLS + job_runs job_kind

Revision ID: 0016_google_integrations
Revises: 0015_iban_history
Create Date: 2026-08-12

Milestone 10 — Google Sheets export (SPEC §47/48/50/51/54). Una riga per
workspace (`uq_google_integrations_workspace`), non una lista di profili:
qui non si confrontano provider, si collega un unico account Google.

Stesso pattern RLS standard di `0003`/`0007`/`0009`/`0010`/`0011`.

Estende anche il CHECK di `job_runs.job_kind` con `google_sheets_export`
(stato persistente dell'ultimo export, stesso pattern di
`market_data_refresh`): va ricreato perche' un CHECK CONSTRAINT non e'
alterabile in-place in Postgres.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016_google_integrations"
down_revision: Union[str, None] = "0015_iban_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_integrations",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("google_account_email", sa.String, nullable=False),
        sa.Column("credentials_encrypted", sa.String, nullable=False),
        sa.Column("spreadsheet_id", sa.String, nullable=False),
        sa.Column("spreadsheet_url", sa.String, nullable=False),
        sa.Column("default_drive_folder_id", sa.String, nullable=True),
        sa.Column("default_drive_folder_name", sa.String, nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", name="uq_google_integrations_workspace"),
    )
    op.create_index("ix_google_integrations_workspace_id", "google_integrations", ["workspace_id"])

    op.execute("ALTER TABLE google_integrations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE google_integrations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY google_integrations_select ON google_integrations FOR SELECT "
        "USING (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY google_integrations_insert ON google_integrations FOR INSERT "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY google_integrations_update ON google_integrations FOR UPDATE "
        "USING (is_workspace_member(workspace_id)) "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY google_integrations_delete ON google_integrations FOR DELETE "
        "USING (is_workspace_member(workspace_id));"
    )

    # --- job_runs.job_kind: aggiungere "google_sheets_export" -----------------
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        "CHECK (job_kind IN ('market_data_refresh', 'snapshot_rebuild', 'google_sheets_export'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        "CHECK (job_kind IN ('market_data_refresh', 'snapshot_rebuild'))"
    )

    op.execute("DROP POLICY IF EXISTS google_integrations_delete ON google_integrations")
    op.execute("DROP POLICY IF EXISTS google_integrations_update ON google_integrations")
    op.execute("DROP POLICY IF EXISTS google_integrations_insert ON google_integrations")
    op.execute("DROP POLICY IF EXISTS google_integrations_select ON google_integrations")
    op.drop_index("ix_google_integrations_workspace_id", table_name="google_integrations")
    op.drop_table("google_integrations")

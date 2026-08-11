"""transaction_type_mappings + RLS

Revision ID: 0012_transaction_type_mappings
Revises: 0011_job_runs
Create Date: 2026-08-11

Milestone 09.5 — mappatura tipi transazione configurabile per parser
(SPEC §17, follow-up dell'hotfix pre-M09 su source_type_raw). Una riga per
(workspace, parser_type, source_type_raw): override esplicito dell'utente
sul default hardcoded del parser, mai il contrario.

Stesso pattern RLS standard di `0003`/`0007`/`0009`/`0010`/`0011`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_transaction_type_mappings"
down_revision: Union[str, None] = "0011_job_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_type_mappings",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parser_type", sa.String, nullable=False),
        sa.Column("source_type_raw", sa.String, nullable=False),
        sa.Column("transaction_type", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "transaction_type IN ("
            "'expense', 'income', 'transfer', 'investment', 'dividend', "
            "'interest', 'fee', 'tax', 'refund', 'adjustment'"
            ")",
            name="ck_transaction_type_mappings_type",
        ),
        sa.UniqueConstraint(
            "workspace_id", "parser_type", "source_type_raw", name="uq_transaction_type_mappings_label"
        ),
    )
    op.create_index(
        "ix_transaction_type_mappings_workspace_id", "transaction_type_mappings", ["workspace_id"]
    )

    op.execute("ALTER TABLE transaction_type_mappings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transaction_type_mappings FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY transaction_type_mappings_select ON transaction_type_mappings FOR SELECT "
        "USING (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY transaction_type_mappings_insert ON transaction_type_mappings FOR INSERT "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY transaction_type_mappings_update ON transaction_type_mappings FOR UPDATE "
        "USING (is_workspace_member(workspace_id)) "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY transaction_type_mappings_delete ON transaction_type_mappings FOR DELETE "
        "USING (is_workspace_member(workspace_id));"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS transaction_type_mappings_delete ON transaction_type_mappings")
    op.execute("DROP POLICY IF EXISTS transaction_type_mappings_update ON transaction_type_mappings")
    op.execute("DROP POLICY IF EXISTS transaction_type_mappings_insert ON transaction_type_mappings")
    op.execute("DROP POLICY IF EXISTS transaction_type_mappings_select ON transaction_type_mappings")
    op.drop_index("ix_transaction_type_mappings_workspace_id", table_name="transaction_type_mappings")
    op.drop_table("transaction_type_mappings")

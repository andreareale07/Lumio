"""asset_profiles (arricchimento asset, Step 3 pagina dettaglio) + RLS

Revision ID: 0028_asset_profiles
Revises: 0027_ai_stale_threshold
Create Date: 2026-08-17

Milestone dashboard interattivo, Step 3 — emittente/categoria/patrimonio del
fondo/accumulo-distribuzione, tutti campi opzionali (SPEC "mai un blocco
della pagina" per un dato di arricchimento assente). Stesso pattern RLS a 4
policy delle altre tabelle asset-scoped (0010). `fetched_at` NOT NULL: una
riga esiste solo dopo un fetch riuscito (anche se tutti i campi sono NULL,
un provider che ha risposto ma non aveva nulla da dire e' comunque una
cache valida, non va ritentato a ogni apertura pagina).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_asset_profiles"
down_revision: Union[str, None] = "0027_ai_stale_threshold"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_profiles",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issuer", sa.String, nullable=True),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("aum", sa.Numeric(24, 2), nullable=True),
        sa.Column("distribution_policy", sa.String, nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "asset_id", name="uq_asset_profiles_asset"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_profiles_workspace_asset",
        ),
    )
    op.create_index("ix_asset_profiles_workspace_id", "asset_profiles", ["workspace_id"])
    op.create_index("ix_asset_profiles_asset_id", "asset_profiles", ["asset_id"])

    op.execute("ALTER TABLE asset_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE asset_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY asset_profiles_select ON asset_profiles FOR SELECT "
        "USING (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY asset_profiles_insert ON asset_profiles FOR INSERT "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY asset_profiles_update ON asset_profiles FOR UPDATE "
        "USING (is_workspace_member(workspace_id)) "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY asset_profiles_delete ON asset_profiles FOR DELETE "
        "USING (is_workspace_member(workspace_id));"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS asset_profiles_delete ON asset_profiles")
    op.execute("DROP POLICY IF EXISTS asset_profiles_update ON asset_profiles")
    op.execute("DROP POLICY IF EXISTS asset_profiles_insert ON asset_profiles")
    op.execute("DROP POLICY IF EXISTS asset_profiles_select ON asset_profiles")
    op.drop_table("asset_profiles")

"""ai_profiles + RLS

Revision ID: 0007_ai_settings
Revises: 0006_rules_classifications
Create Date: 2026-08-11

Milestone 07 — AI Abstraction (SPEC §25-28).

`ai_profiles` e' tenant-scoped come `financial_accounts` (workspace_id
diretto, stesso pattern RLS a 4 policy), ma senza UNIQUE su workspace_id:
un workspace puo' salvare PIU' profili (anche dello stesso provider — es.
due endpoint Ollama diversi), non uno solo come nella prima versione di
questa migration. Al massimo UNO per workspace ha `is_active=true`,
garantito da un indice UNIQUE parziale
(`uq_ai_profiles_one_active_per_workspace`) — mutua esclusivita' a livello
DB, non solo applicativo. Nessun profilo attivo equivale semplicemente ad
"AI disabilitata" per il workspace (SPEC §25): non esiste una riga
"provider=none" a se stante.

`api_key_encrypted` e' sempre cifrato a riposo (Fernet,
`app/core/crypto.py`) prima di arrivare qui — questa migration non sa nulla
del contenuto, e' semplicemente una colonna String.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_ai_settings"
down_revision: Union[str, None] = "0006_rules_classifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("endpoint", sa.String, nullable=True),
        sa.Column("model", sa.String, nullable=True),
        sa.Column("api_key_encrypted", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "provider IN ('ollama', 'openai', 'anthropic', 'custom')",
            name="ck_ai_profiles_provider",
        ),
    )
    op.create_index("ix_ai_profiles_workspace_id", "ai_profiles", ["workspace_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_ai_profiles_one_active_per_workspace "
        "ON ai_profiles (workspace_id) WHERE is_active"
    )

    op.execute("ALTER TABLE ai_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ai_profiles_select ON ai_profiles FOR SELECT
        USING (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY ai_profiles_insert ON ai_profiles FOR INSERT
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY ai_profiles_update ON ai_profiles FOR UPDATE
        USING (is_workspace_member(workspace_id))
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY ai_profiles_delete ON ai_profiles FOR DELETE
        USING (is_workspace_member(workspace_id));
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ai_profiles_delete ON ai_profiles")
    op.execute("DROP POLICY IF EXISTS ai_profiles_update ON ai_profiles")
    op.execute("DROP POLICY IF EXISTS ai_profiles_insert ON ai_profiles")
    op.execute("DROP POLICY IF EXISTS ai_profiles_select ON ai_profiles")
    op.execute("DROP INDEX IF EXISTS uq_ai_profiles_one_active_per_workspace")
    op.drop_index("ix_ai_profiles_workspace_id", table_name="ai_profiles")
    op.drop_table("ai_profiles")

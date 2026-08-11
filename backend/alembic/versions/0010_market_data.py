"""market_data_profiles, asset_prices, portfolio_snapshots, net_worth_snapshots + RLS

Revision ID: 0010_market_data
Revises: 0009_portfolio_domain
Create Date: 2026-08-11

Milestone 09b — Market Data + Snapshot (SPEC §38, §31, §37).

Stesso pattern RLS standard di `0003`/`0007`/`0009` per tutte le 4 tabelle:
`ENABLE`+`FORCE ROW LEVEL SECURITY`, 4 policy separate su
`is_workspace_member(workspace_id)`.

- `market_data_profiles`: clone strutturale di `ai_profiles` (M07) — piu'
  profili per workspace, indice UNIQUE parziale per garantire al massimo un
  attivo (`uq_market_data_profiles_one_active_per_workspace`).
- `asset_prices`: storico prezzi, sia manuali sia scaricati da un provider
  (stessa tabella, `source` diversa) — un solo prezzo per (asset, giorno).
- `portfolio_snapshots`: `portfolio_id` NULL rappresenta l'aggregato
  implicito "tutti i conti". NULL non e' mai "uguale" a se stesso in un
  UNIQUE standard, quindi l'unicita' "un solo aggregato al giorno" richiede
  due indici parziali distinti (uno per riga con portfolio, uno per
  l'aggregato) invece di un singolo UNIQUE su 3 colonne.
- `net_worth_snapshots`: risponde a una domanda diversa (patrimonio
  complessivo, non il valore di un portfolio) — un solo snapshot al giorno
  per workspace.

Aggiunta anche la funzione `list_workspace_owners()`, SECURITY DEFINER di
proprieta' di `lumio_rls_helper` (stesso pattern di `is_workspace_member`,
migration 0002): serve ai job schedulati del worker
(`app/worker/jobs/market_data.py`, `app/worker/jobs/snapshot.py`), che
girano senza una richiesta HTTP e quindi senza nessun `app.current_user_id`
gia' impostato — senza questa funzione, `workspaces` (RLS-protetta) non
sarebbe enumerabile affatto. Un varco stretto e verificabile (ritorna solo
`workspace_id`/`owner_user_id`, mai altri dati), non un bypass generale: il
job apre poi una `rls_session(owner_user_id)` per ogni workspace, mai
`SET ROLE lumio_rls_helper` nel path applicativo (CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_market_data"
down_revision: Union[str, None] = "0009_portfolio_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- list_workspace_owners() (SECURITY DEFINER, per i job schedulati) ---

    op.execute(
        """
        CREATE FUNCTION list_workspace_owners()
        RETURNS TABLE(workspace_id uuid, owner_user_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        AS $$
            SELECT id, owner_user_id FROM workspaces;
        $$;
        """
    )
    op.execute("ALTER FUNCTION list_workspace_owners() OWNER TO lumio_rls_helper")

    # --- market_data_profiles ---------------------------------------------

    op.create_table(
        "market_data_profiles",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
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
        sa.Column("api_key_encrypted", sa.String, nullable=True),
        sa.Column("price_field", sa.String, nullable=True),
        sa.Column("currency_field", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "provider IN ('manual', 'stooq', 'yahoo', 'custom')",
            name="ck_market_data_profiles_provider",
        ),
    )
    op.create_index("ix_market_data_profiles_workspace_id", "market_data_profiles", ["workspace_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_market_data_profiles_one_active_per_workspace "
        "ON market_data_profiles (workspace_id) WHERE is_active"
    )

    # --- asset_prices -----------------------------------------------------

    op.create_table(
        "asset_prices",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("price_date", sa.Date, nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "source IN ('manual', 'stooq', 'yahoo', 'custom')", name="ck_asset_prices_source"
        ),
        sa.UniqueConstraint("workspace_id", "asset_id", "price_date", name="uq_asset_prices_asset_date"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_prices_workspace_asset",
        ),
    )
    op.create_index("ix_asset_prices_workspace_id", "asset_prices", ["workspace_id"])
    op.create_index("ix_asset_prices_asset_id", "asset_prices", ["asset_id"])

    # --- portfolio_snapshots ------------------------------------------------

    op.create_table(
        "portfolio_snapshots",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("market_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 2), nullable=False),
        sa.Column("unrealized_pl", sa.Numeric(18, 2), nullable=False),
        sa.Column("realized_pl", sa.Numeric(18, 2), nullable=False),
        sa.Column("has_market_data", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            ondelete="CASCADE",
            name="fk_portfolio_snapshots_workspace_portfolio",
        ),
    )
    op.create_index("ix_portfolio_snapshots_workspace_id", "portfolio_snapshots", ["workspace_id"])
    op.create_index("ix_portfolio_snapshots_portfolio_id", "portfolio_snapshots", ["portfolio_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_portfolio_snapshots_portfolio_date "
        "ON portfolio_snapshots (workspace_id, portfolio_id, snapshot_date) "
        "WHERE portfolio_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_portfolio_snapshots_aggregate_date "
        "ON portfolio_snapshots (workspace_id, snapshot_date) "
        "WHERE portfolio_id IS NULL"
    )

    # --- net_worth_snapshots -------------------------------------------------

    op.create_table(
        "net_worth_snapshots",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("liquidity", sa.Numeric(18, 2), nullable=False),
        sa.Column("debt", sa.Numeric(18, 2), nullable=False),
        sa.Column("investments", sa.Numeric(18, 2), nullable=False),
        sa.Column("net_worth", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "snapshot_date", name="uq_net_worth_snapshots_workspace_date"),
    )
    op.create_index("ix_net_worth_snapshots_workspace_id", "net_worth_snapshots", ["workspace_id"])

    # --- Row-Level Security: stesso pattern a 4 policy per ogni tabella --------

    for table in ("market_data_profiles", "asset_prices", "portfolio_snapshots", "net_worth_snapshots"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_select ON {table} FOR SELECT "
            "USING (is_workspace_member(workspace_id));"
        )
        op.execute(
            f"CREATE POLICY {table}_insert ON {table} FOR INSERT "
            "WITH CHECK (is_workspace_member(workspace_id));"
        )
        op.execute(
            f"CREATE POLICY {table}_update ON {table} FOR UPDATE "
            "USING (is_workspace_member(workspace_id)) "
            "WITH CHECK (is_workspace_member(workspace_id));"
        )
        op.execute(
            f"CREATE POLICY {table}_delete ON {table} FOR DELETE "
            "USING (is_workspace_member(workspace_id));"
        )


def downgrade() -> None:
    for table in ("net_worth_snapshots", "portfolio_snapshots", "asset_prices", "market_data_profiles"):
        op.execute(f"DROP POLICY IF EXISTS {table}_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_select ON {table}")

    op.drop_table("net_worth_snapshots")

    op.execute("DROP INDEX IF EXISTS uq_portfolio_snapshots_aggregate_date")
    op.execute("DROP INDEX IF EXISTS uq_portfolio_snapshots_portfolio_date")
    op.drop_table("portfolio_snapshots")

    op.drop_table("asset_prices")

    op.execute("DROP INDEX IF EXISTS uq_market_data_profiles_one_active_per_workspace")
    op.drop_index("ix_market_data_profiles_workspace_id", table_name="market_data_profiles")
    op.drop_table("market_data_profiles")

    op.execute("DROP FUNCTION IF EXISTS list_workspace_owners()")

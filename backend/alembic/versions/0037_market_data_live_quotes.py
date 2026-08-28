"""market_data_profiles: refresh interval configurabile + asset_price_quotes (intraday)

Revision ID: 0037_market_data_live_quotes
Revises: 0036_snapshot_backfill_job
Create Date: 2026-08-28

docs/SPEC_STOCK_PRICE.md: separazione esplicita tra prezzo daily canonico
(`asset_prices`, INVARIATA — nessuna colonna aggiunta, nessun dato
migrato), dati intraday osservati (nuova `asset_price_quotes`, mai letta
da valorizzazione/snapshot) e latest-quote live (Redis, fuori da questa
migration).

`portfolio_refresh_interval_seconds`/`detail_refresh_interval_seconds` su
`market_data_profiles`: intervallo MINIMO tra due chiamate reali al
provider (non un TTL esatto) — rispettivamente per il refresh bulk
(posizioni aperte, in background) e per la live-quote di un singolo asset
(cache Redis, TTL = questo valore + 5s). `NOT NULL` con `server_default`:
i profili esistenti ottengono il default senza alcun passo di backfill
separato (backward compatible per costruzione).

`asset_price_quotes`: una riga per quotazione osservata (non un upsert su
un solo valore corrente) — popolata SOLO quando la live-quote cache ha un
miss reale (mai quando si serve dalla cache Redis), e dal fallback del
grafico "1G"/"1S" quando il fetch live del provider viene comunque fatto
(vedi `app/api/v1/assets.py`). Stesso pattern RLS a 4 policy di
`0010_market_data` per tutte le tabelle di questo dominio.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0037_market_data_live_quotes"
down_revision: Union[str, None] = "0036_snapshot_backfill_job"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "market_data_profiles",
        sa.Column(
            "portfolio_refresh_interval_seconds",
            sa.Integer,
            nullable=False,
            server_default=sa.text("900"),
        ),
    )
    op.add_column(
        "market_data_profiles",
        sa.Column(
            "detail_refresh_interval_seconds",
            sa.Integer,
            nullable=False,
            server_default=sa.text("15"),
        ),
    )
    op.create_check_constraint(
        "ck_market_data_profiles_portfolio_refresh_interval",
        "market_data_profiles",
        "portfolio_refresh_interval_seconds BETWEEN 300 AND 86400",
    )
    op.create_check_constraint(
        "ck_market_data_profiles_detail_refresh_interval",
        "market_data_profiles",
        "detail_refresh_interval_seconds BETWEEN 5 AND 3600",
    )

    op.create_table(
        "asset_price_quotes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "source IN ('stooq', 'yahoo', 'custom')", name="ck_asset_price_quotes_source"
        ),
        sa.UniqueConstraint(
            "workspace_id", "asset_id", "quoted_at", name="uq_asset_price_quotes_asset_quoted_at"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_price_quotes_workspace_asset",
        ),
    )
    op.create_index("ix_asset_price_quotes_workspace_id", "asset_price_quotes", ["workspace_id"])
    op.create_index("ix_asset_price_quotes_asset_id", "asset_price_quotes", ["asset_id"])

    for table in ("asset_price_quotes",):
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
    op.execute("DROP POLICY IF EXISTS asset_price_quotes_delete ON asset_price_quotes")
    op.execute("DROP POLICY IF EXISTS asset_price_quotes_update ON asset_price_quotes")
    op.execute("DROP POLICY IF EXISTS asset_price_quotes_insert ON asset_price_quotes")
    op.execute("DROP POLICY IF EXISTS asset_price_quotes_select ON asset_price_quotes")
    op.drop_table("asset_price_quotes")

    op.drop_constraint(
        "ck_market_data_profiles_detail_refresh_interval", "market_data_profiles", type_="check"
    )
    op.drop_constraint(
        "ck_market_data_profiles_portfolio_refresh_interval", "market_data_profiles", type_="check"
    )
    op.drop_column("market_data_profiles", "detail_refresh_interval_seconds")
    op.drop_column("market_data_profiles", "portfolio_refresh_interval_seconds")

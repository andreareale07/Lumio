"""dominio Portfolio (M09a) + hotfix source_type_raw

Revision ID: 0009_portfolio_domain
Revises: 0008_analytics_indexes
Create Date: 2026-08-11

Milestone 09 — Portfolio (SPEC §31-38), preceduta da un hotfix indipendente
sui tipi di transazione.

## Hotfix pre-M09: `transactions.source_type_raw`

Emerso analizzando M09: il parser Trade Republic mappava l'etichetta
"Bonifico" su `transaction_type="transfer"`, che gli analytics escludono dal
cash flow (`analytics.py:_EXCLUDED_FROM_CASH_FLOW`) — ogni bonifico in
entrata o uscita spariva silenziosamente da entrate/spese (bug osservato su
dati reali). "Bonifico" e' uno STRUMENTO di pagamento, non un tipo semantico:
non e' mai deducibile a `transfer` da un solo estratto conto (SPEC §21, il
pairing tra le due transazioni gemelle resta rimandato). Il fix vero e' nel
codice del parser (`app/parsers/trade_republic.py`); qui si aggiunge solo la
colonna che permette di conservare il dato raw invece di scartarlo (CLAUDE.md:
"conservare sempre il dato raw insieme al normalizzato") — nullable, nessun
backfill possibile sui dati gia' importati prima di questa colonna.

## Dominio Portfolio (M09a)

Cinque tabelle nuove, tutte tenant-scoped, stesso pattern RLS standard di
`0003`/`0007`: `ENABLE`+`FORCE ROW LEVEL SECURITY`, 4 policy separate
(select/insert/update/delete, mai `FOR ALL`) su `is_workspace_member`.
Ogni tabella "genitore" referenziata da altre porta
`UniqueConstraint(workspace_id, id)` per abilitare FK composite dalle
tabelle figlie (SPEC §57, "mai fidarsi solo della RLS") — questo vale anche
per `transactions`, che finora non ne aveva bisogno (nessuna tabella FK-ava
al suo interno) e qui la riceve per abilitare
`investment_transactions.transaction_id`.

- `assets`: catalogo per workspace (non globale come `banks` — un catalogo
  condiviso esporrebbe asset creati da un utente a tutti gli altri tenant).
  Unique parziali case-insensitive su `(workspace_id, isin)` e
  `(workspace_id, upper(symbol))` dove non nulli.
- `portfolios` + `portfolio_accounts`: portfolio aggregabili su piu' conti
  (SPEC §36). "Tutti i conti" resta una vista implicita in UI, non una riga.
- `investment_transactions`: libro mastro, unica sorgente di verita' per le
  posizioni (mai un secondo modello da riconciliare). `asset_id` nullable
  (deposit/withdrawal/fee possono non riferirsi a un titolo);
  `transaction_id` nullable e SET NULL verso la transazione bancaria
  corrispondente — link opzionale, mai una scrittura duplicata del cash
  (che scende gia' dall'estratto conto importato).
- `positions`: materializzata ma sempre DERIVATA dai movimenti
  (`app/services/position_service.py:recompute_position`), mai una seconda
  fonte di verita' indipendente. Si lega a `financial_account_id`, MAI
  all'`account_type` del conto (decisione M08 confermata: un conto
  "checking" puo' avere posizioni reali).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_portfolio_domain"
down_revision: Union[str, None] = "0008_analytics_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- hotfix pre-M09 ---------------------------------------------------

    op.add_column("transactions", sa.Column("source_type_raw", sa.String(), nullable=True))
    op.create_unique_constraint("uq_transactions_workspace_id", "transactions", ["workspace_id", "id"])

    # --- assets -------------------------------------------------------------

    op.create_table(
        "assets",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String, nullable=True),
        sa.Column("isin", sa.String, nullable=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("asset_type", sa.String, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "asset_type IN ('etf', 'stock', 'bond', 'crypto', 'fund', 'cash', 'other')",
            name="ck_assets_asset_type",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_assets_workspace_id"),
    )
    op.create_index("ix_assets_workspace_id", "assets", ["workspace_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_assets_workspace_isin ON assets (workspace_id, isin) "
        "WHERE isin IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_assets_workspace_symbol ON assets (workspace_id, upper(symbol)) "
        "WHERE symbol IS NOT NULL"
    )

    # --- portfolios -----------------------------------------------------------

    op.create_table(
        "portfolios",
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
        sa.Column("description", sa.String, nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "name", name="uq_portfolios_workspace_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_portfolios_workspace_id"),
    )
    op.create_index("ix_portfolios_workspace_id", "portfolios", ["workspace_id"])

    # --- portfolio_accounts (join M2M) -----------------------------------------

    op.create_table(
        "portfolio_accounts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "workspace_id", "portfolio_id", "financial_account_id",
            name="uq_portfolio_accounts_portfolio_account",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            ondelete="CASCADE",
            name="fk_portfolio_accounts_workspace_portfolio",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_portfolio_accounts_workspace_account",
        ),
    )
    op.create_index("ix_portfolio_accounts_workspace_id", "portfolio_accounts", ["workspace_id"])
    op.create_index("ix_portfolio_accounts_portfolio_id", "portfolio_accounts", ["portfolio_id"])
    op.create_index(
        "ix_portfolio_accounts_financial_account_id", "portfolio_accounts", ["financial_account_id"]
    )

    # --- investment_transactions (libro mastro) --------------------------------

    op.create_table(
        "investment_transactions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("quantity", sa.Numeric(28, 10), nullable=True),
        sa.Column("price", sa.Numeric(18, 6), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("fees", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("tax", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_type_raw", sa.String, nullable=True),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "type IN ('buy', 'sell', 'dividend', 'deposit', 'withdrawal', "
            "'fee', 'tax', 'split', 'opening', 'adjustment')",
            name="ck_investment_transactions_type",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_investment_transactions_workspace_account",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="RESTRICT",
            name="fk_investment_transactions_workspace_asset",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="SET NULL",
            name="fk_investment_transactions_workspace_transaction",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_investment_transactions_workspace_id"),
    )
    op.create_index("ix_investment_transactions_workspace_id", "investment_transactions", ["workspace_id"])
    op.create_index(
        "ix_investment_transactions_financial_account_id",
        "investment_transactions",
        ["financial_account_id"],
    )
    op.create_index("ix_investment_transactions_asset_id", "investment_transactions", ["asset_id"])

    # --- positions (sempre derivata) --------------------------------------------

    op.create_table(
        "positions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 10), nullable=False, server_default=sa.text("0")),
        sa.Column("average_cost", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("realized_pl", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "workspace_id", "financial_account_id", "asset_id", name="uq_positions_account_asset"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_positions_workspace_account",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_positions_workspace_asset",
        ),
    )
    op.create_index("ix_positions_workspace_id", "positions", ["workspace_id"])
    op.create_index("ix_positions_financial_account_id", "positions", ["financial_account_id"])
    op.create_index("ix_positions_asset_id", "positions", ["asset_id"])

    # --- Row-Level Security: stesso pattern a 4 policy per ogni tabella --------

    for table in ("assets", "portfolios", "portfolio_accounts", "investment_transactions", "positions"):
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
    for table in ("positions", "investment_transactions", "portfolio_accounts", "portfolios", "assets"):
        op.execute(f"DROP POLICY IF EXISTS {table}_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_select ON {table}")

    op.drop_table("positions")
    op.drop_table("investment_transactions")
    op.drop_table("portfolio_accounts")

    op.drop_index("ix_portfolios_workspace_id", table_name="portfolios")
    op.drop_table("portfolios")

    op.execute("DROP INDEX IF EXISTS uq_assets_workspace_symbol")
    op.execute("DROP INDEX IF EXISTS uq_assets_workspace_isin")
    op.drop_index("ix_assets_workspace_id", table_name="assets")
    op.drop_table("assets")

    op.drop_constraint("uq_transactions_workspace_id", "transactions", type_="unique")
    op.drop_column("transactions", "source_type_raw")

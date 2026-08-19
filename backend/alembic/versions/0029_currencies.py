"""currencies (tabella di sistema) + fx_rates (globale) + workspaces.base_currency

Revision ID: 0029_currencies
Revises: 0028_asset_profiles
Create Date: 2026-08-17

Sistema di valute — bug reale corretto in questa milestone: le funzioni di
`portfolio_analytics.py`/`analytics.py` escludevano silenziosamente ogni
riga la cui valuta non coincideva con quella risolta per la richiesta
(nessuna conversione, decisione M08). Qui si introduce l'infrastruttura
dati: una tabella di sistema `currencies` (stesso pattern di `categories`,
migration 0003 — righe con `workspace_id IS NULL` visibili a tutti via RLS
— con una differenza deliberata: `code` e' la PRIMARY KEY, globalmente
univoca, nessuna coppia `(workspace_id, code)` ne' trigger anti-shadowing
serve per un codice gia' universale come una valuta) e `fx_rates`
(GLOBALE, nessun `workspace_id`, nessuna RLS: un tasso di cambio e' un
fatto di mercato oggettivo, non un dato di tenant — una riga scaricata da
QUALUNQUE workspace beneficia tutti gli altri).

`workspaces.base_currency` sostituisce l'euristica automatica di
`resolve_currency` ("valuta prevalente tra i conti") con un'impostazione
esplicita — il backfill qui sotto calcola pero' la STESSA euristica per i
workspace esistenti, cosi' il comportamento effettivo di oggi non cambia
finche' l'utente non la modifica esplicitamente in Impostazioni.

FK da tutte le colonne "currency" del dominio verso `currencies.code`:
verificato sui dati reali (solo EUR/USD in uso) prima di scrivere questa
migration, nessun rischio di rottura per codici non coperti dal seed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.currency_catalog import SEED_CURRENCIES

revision: str = "0029_currencies"
down_revision: Union[str, None] = "0028_asset_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tutte le tabelle di dominio con una colonna "currency" — vedi docstring:
# stesso codice, mai un id sintetico, la FK punta direttamente a currencies.code.
_CURRENCY_FK_TABLES = [
    "assets",
    "financial_accounts",
    "transactions",
    "investment_transactions",
    "asset_prices",
    "positions",
    "portfolios",
    "portfolio_snapshots",
    "net_worth_snapshots",
]


def upgrade() -> None:
    # --- currencies (tabella di sistema) ------------------------------------

    op.create_table(
        "currencies",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("symbol", sa.String(8), nullable=False),
        sa.Column("decimal_digits", sa.Integer, nullable=False, server_default=sa.text("2")),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_currencies_workspace_id", "currencies", ["workspace_id"])

    # Seed PRIMA di abilitare la RLS (stesso ordine del seed tassonomia
    # categorie, migration 0003): con FORCE ROW LEVEL SECURITY gia' attivo,
    # nessuna policy INSERT ammette workspace_id NULL, nemmeno per il
    # proprietario della tabella — le righe di sistema vanno scritte mentre
    # la tabella e' ancora "aperta".
    currencies_table = sa.table(
        "currencies",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("symbol", sa.String),
        sa.column("decimal_digits", sa.Integer),
        sa.column("is_system", sa.Boolean),
    )
    op.bulk_insert(
        currencies_table,
        [
            {
                "code": c.code,
                "name": c.name,
                "symbol": c.symbol,
                "decimal_digits": c.decimal_digits,
                "is_system": True,
            }
            for c in SEED_CURRENCIES
        ],
    )

    op.execute("ALTER TABLE currencies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE currencies FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY currencies_select ON currencies FOR SELECT "
        "USING (workspace_id IS NULL OR is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY currencies_insert ON currencies FOR INSERT "
        "WITH CHECK (workspace_id IS NOT NULL AND is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY currencies_update ON currencies FOR UPDATE "
        "USING (workspace_id IS NOT NULL AND is_workspace_member(workspace_id) AND NOT is_system) "
        "WITH CHECK (workspace_id IS NOT NULL AND is_workspace_member(workspace_id) AND NOT is_system);"
    )
    op.execute(
        "CREATE POLICY currencies_delete ON currencies FOR DELETE "
        "USING (workspace_id IS NOT NULL AND is_workspace_member(workspace_id) AND NOT is_system);"
    )
    # BYPASSRLS bypassa le *policy* ma non i normali GRANT (stessa nota gia'
    # presente per `categories`, migration 0003): lumio_rls_helper deve
    # poter scrivere le valute di sistema per un eventuale reseed futuro.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON currencies TO lumio_rls_helper")

    # --- fx_rates (GLOBALE: nessun workspace_id, nessuna RLS) ---------------

    op.create_table(
        "fx_rates",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("from_currency", sa.String(10), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("to_currency", sa.String(10), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("rate_date", sa.Date, nullable=False),
        sa.Column("rate", sa.Numeric(24, 10), nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "source IN ('manual', 'stooq', 'yahoo', 'custom')", name="ck_fx_rates_source"
        ),
        sa.UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_rates_pair_date"),
    )
    op.create_index("ix_fx_rates_from_currency", "fx_rates", ["from_currency"])
    op.create_index("ix_fx_rates_to_currency", "fx_rates", ["to_currency"])

    # --- workspaces.base_currency --------------------------------------------

    op.add_column(
        "workspaces",
        sa.Column(
            "base_currency", sa.String(10), sa.ForeignKey("currencies.code"), nullable=False,
            server_default=sa.text("'EUR'"),
        ),
    )
    # Backfill: STESSA euristica di analytics.resolve_currency oggi (valuta
    # con piu' conti nel workspace) — preserva il comportamento effettivo
    # attuale, non forza EUR a chi gia' opera in un'altra valuta.
    op.execute(
        """
        WITH counts AS (
            SELECT workspace_id, currency, COUNT(*) AS n
            FROM financial_accounts
            GROUP BY workspace_id, currency
        ),
        ranked AS (
            SELECT workspace_id, currency,
                   ROW_NUMBER() OVER (PARTITION BY workspace_id ORDER BY n DESC) AS rn
            FROM counts
        )
        UPDATE workspaces w
        SET base_currency = r.currency
        FROM ranked r
        WHERE r.workspace_id = w.id AND r.rn = 1;
        """
    )

    # --- FK "currency" -> currencies.code su tutto il dominio ----------------

    for table in _CURRENCY_FK_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_currency "
            f"FOREIGN KEY (currency) REFERENCES currencies(code)"
        )


def downgrade() -> None:
    for table in _CURRENCY_FK_TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_currency")

    op.drop_column("workspaces", "base_currency")

    op.drop_index("ix_fx_rates_to_currency", table_name="fx_rates")
    op.drop_index("ix_fx_rates_from_currency", table_name="fx_rates")
    op.drop_table("fx_rates")

    op.execute("DROP POLICY IF EXISTS currencies_delete ON currencies")
    op.execute("DROP POLICY IF EXISTS currencies_update ON currencies")
    op.execute("DROP POLICY IF EXISTS currencies_insert ON currencies")
    op.execute("DROP POLICY IF EXISTS currencies_select ON currencies")
    op.drop_index("ix_currencies_workspace_id", table_name="currencies")
    op.drop_table("currencies")

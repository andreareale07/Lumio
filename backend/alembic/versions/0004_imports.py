"""import_mappings, imports, transactions.import_id + RLS

Revision ID: 0004_imports
Revises: 0003_accounts_transactions
Create Date: 2026-08-10

Milestone 04 — Import Engine.

Ordine di creazione dettato dalle dipendenze FK: `import_mappings` prima di
`imports` (che la referenzia via FK composita), `imports` prima di
aggiungere `transactions.import_id`.

Cross-tenant a livello DB (SPEC §57), pattern riusato da M03:
- `import_mappings.financial_account_id` e `imports.financial_account_id`
  usano FK composite `(workspace_id, id)` verso `financial_accounts` —
  nessun trigger necessario perche' `financial_accounts.workspace_id` non e'
  mai NULL: con MATCH SIMPLE (il default Postgres) una FK composita e'
  soddisfatta automaticamente quando la colonna referenziante e' NULL, e
  quando non lo e' entrambe le colonne sono confrontate. Il trigger di M03
  (`check_transaction_category_workspace`) serviva per un motivo diverso: li'
  era la riga *referenziata* (categories) a poter avere workspace_id NULL
  (categorie di sistema), non la colonna referenziante.
- Stesso discorso per `imports.import_mapping_id` -> `import_mappings`.
- `transactions.import_id` -> `imports`: stessa FK composita, ma con
  ON DELETE RESTRICT invece di CASCADE — a differenza degli altri casi,
  cancellare un import non deve mai poter far sparire silenziosamente
  transazioni finanziarie reali gia' importate. Nessun endpoint DELETE su
  imports esiste in questa milestone, quindi il RESTRICT non blocca nessun
  flusso applicativo attuale.

Dedup (SPEC §58): indice unico PARZIALE `(workspace_id, file_hash)` che
esclude gli stati `failed`/`cancelled` — un file puo' essere ricaricato dopo
un tentativo fallito o annullato, ma due file identici "attivi" nello stesso
workspace non possono mai coesistere. La garanzia e' a livello DB (un check
applicativo con SELECT-poi-INSERT sarebbe soggetto a race tra richieste
concorrenti), incluso contro un ipotetico bug applicativo.

RLS: stesso pattern di 0003 — ENABLE + FORCE, `is_workspace_member` (gia'
definita in 0002) riusata cosi' com'e' per tutte e 4 le policy per comando.
Nessuna riga "di sistema" su queste tabelle, quindi nessun GRANT aggiuntivo a
lumio_rls_helper e' necessario (a differenza di categories in M03).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_imports"
down_revision: Union[str, None] = "0003_accounts_transactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMPORT_STATUSES = (
    "uploaded",
    "queued",
    "processing",
    "parsing",
    "classifying",
    "ready_for_review",
    "completed",
    "failed",
    "cancelled",
)


def upgrade() -> None:
    # --- import_mappings --------------------------------------------------

    op.create_table(
        "import_mappings",
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
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "name", name="uq_import_mappings_workspace_name"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_import_mappings_workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_import_mappings_workspace_account",
        ),
    )
    op.create_index("ix_import_mappings_workspace_id", "import_mappings", ["workspace_id"])

    # --- imports ------------------------------------------------------------

    op.create_table(
        "imports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("import_mapping_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Snapshot immutabile della mappatura EFFETTIVAMENTE usata per questo
        # import (impostato da POST /confirm), indipendente da
        # import_mapping_id: quest'ultimo punta a una mappatura riusabile
        # SALVATA, ma l'utente puo' confermare anche con una mappatura
        # inline mai salvata — in quel caso e' questa colonna, non
        # import_mapping_id, l'unico posto dove il worker puo' recuperare i
        # parametri di parsing. Nullable perche' non esiste ancora quando lo
        # stato e' 'uploaded' (prima della conferma).
        sa.Column("mapping_config", postgresql.JSONB, nullable=True),
        sa.Column("job_id", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'uploaded'")),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("transactions_found", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("transactions_imported", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in IMPORT_STATUSES) + ")",
            name="ck_imports_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_imports_workspace_account",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "import_mapping_id"],
            ["import_mappings.workspace_id", "import_mappings.id"],
            ondelete="SET NULL",
            name="fk_imports_workspace_mapping",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_imports_workspace_id"),
    )
    op.create_index("ix_imports_workspace_id", "imports", ["workspace_id"])
    op.create_index("ix_imports_financial_account_id", "imports", ["financial_account_id"])
    op.create_index("ix_imports_status", "imports", ["status"])
    # Dedup (SPEC §58): vedi docstring in cima al file.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_imports_workspace_file_hash_active
        ON imports (workspace_id, file_hash)
        WHERE status NOT IN ('failed', 'cancelled');
        """
    )

    # --- transactions.import_id ---------------------------------------------

    op.add_column("transactions", sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_transactions_import_id", "transactions", ["import_id"])
    op.create_foreign_key(
        "fk_transactions_workspace_import",
        "transactions",
        "imports",
        ["workspace_id", "import_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )

    # --- Row-Level Security ---------------------------------------------------

    for table in ("import_mappings", "imports"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_select ON {table} FOR SELECT
            USING (is_workspace_member(workspace_id));
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_insert ON {table} FOR INSERT
            WITH CHECK (is_workspace_member(workspace_id));
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_update ON {table} FOR UPDATE
            USING (is_workspace_member(workspace_id))
            WITH CHECK (is_workspace_member(workspace_id));
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_delete ON {table} FOR DELETE
            USING (is_workspace_member(workspace_id));
            """
        )


def downgrade() -> None:
    op.drop_constraint("fk_transactions_workspace_import", "transactions", type_="foreignkey")
    op.drop_index("ix_transactions_import_id", table_name="transactions")
    op.drop_column("transactions", "import_id")

    for table in ("imports", "import_mappings"):
        op.execute(f"DROP POLICY IF EXISTS {table}_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_select ON {table}")

    op.drop_index("uq_imports_workspace_file_hash_active", table_name="imports")
    op.drop_index("ix_imports_status", table_name="imports")
    op.drop_index("ix_imports_financial_account_id", table_name="imports")
    op.drop_index("ix_imports_workspace_id", table_name="imports")
    op.drop_table("imports")

    op.drop_index("ix_import_mappings_workspace_id", table_name="import_mappings")
    op.drop_table("import_mappings")

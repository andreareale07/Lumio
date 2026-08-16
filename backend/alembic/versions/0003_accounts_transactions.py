"""banks, financial_accounts, categories, transactions + RLS

Revision ID: 0003_accounts_transactions
Revises: 0002_users_workspaces
Create Date: 2026-08-10

Milestone 03 — Accounts + Transactions.

`banks` e' un'entita' globale (non tenant-scoped): nessuna RLS. lumio_app e'
il proprietario della tabella (la crea via questa migration, come tutte le
altre) quindi ha gia' tutti i privilegi necessari senza GRANT espliciti;
l'app la legge ma non la scrive in questa milestone — la gestione dinamica
delle banche non e' nello scope.

Per `financial_accounts`, `categories`, `transactions` si applica lo stesso
pattern RLS di 0002 (ENABLE + FORCE, is_workspace_member riusata cosi'
com'e', nessuna nuova funzione SECURITY DEFINER necessaria perche' queste
tabelle hanno tutte una colonna workspace_id diretta, senza il problema di
bootstrap circolare che aveva workspace_members). A differenza di 0002,
qui servono anche le policy UPDATE/DELETE: il DoD di questa milestone
richiede CRUD completo, non solo lettura/creazione.

Isolamento cross-tenant a livello DB (SPEC §57):
- financial_accounts ha UNIQUE(workspace_id, id); transactions referenzia
  (workspace_id, financial_account_id) con una FK composita verso quella
  coppia. Questo garantisce che un conto di un altro workspace non possa
  MAI essere agganciato a una transazione, indipendentemente da bug
  applicativi o dalla RLS.
- categories puo' avere workspace_id NULL (categorie di sistema), quindi la
  stessa FK composita non e' applicabile (NULL non "matcha" mai in un
  confronto di uguaglianza). ATTENZIONE, assunzione iniziale sbagliata poi
  corretta: PostgreSQL NON applica la RLS della tabella referenziata quando
  verifica un vincolo FK (i controlli di integrita' referenziale bypassano
  le row security policy, indipendentemente da FORCE) — una semplice FK su
  category_id non blocca affatto il cross-tenant, come provato da un test
  dedicato che falliva con quella sola FK. L'isolamento reale e' garantito
  da un trigger BEFORE INSERT OR UPDATE (check_transaction_category_workspace)
  che verifica esplicitamente che la categoria sia di sistema o appartenga
  allo stesso workspace della transazione, con una query eseguita da una
  funzione SECURITY DEFINER (lumio_rls_helper, BYPASSRLS) per non dipendere
  a sua volta da cosa la RLS lascia visibile alla sessione corrente.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.seed_data import BANKS, SYSTEM_CATEGORIES_V1

# revision identifiers, used by Alembic.
revision: str = "0003_accounts_transactions"
down_revision: Union[str, None] = "0002_users_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- banks (globale, no RLS) --------------------------------------------

    op.create_table(
        "banks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("country", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_banks_code", "banks", ["code"])

    banks_table = sa.table(
        "banks",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("country", sa.String),
    )
    op.bulk_insert(
        banks_table,
        [{**bank, "id": uuid.UUID(bank["id"])} for bank in BANKS],
    )

    # --- financial_accounts --------------------------------------------------

    op.create_table(
        "financial_accounts",
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
        sa.Column(
            "bank_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("banks.id"), nullable=True
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("account_type", sa.String, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("account_identifier_masked", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "account_type IN ('checking', 'savings', 'brokerage', 'cash', 'credit_card', 'other')",
            name="ck_financial_accounts_account_type",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_financial_accounts_workspace_id"),
    )
    op.create_index(
        "ix_financial_accounts_workspace_id", "financial_accounts", ["workspace_id"]
    )

    # --- categories -----------------------------------------------------------

    op.create_table(
        "categories",
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
            nullable=True,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("code", sa.String, nullable=False),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_categories_workspace_id", "categories", ["workspace_id"])

    # --- transactions -----------------------------------------------------------

    op.create_table(
        "transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id"),
            nullable=True,
        ),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("value_date", sa.Date, nullable=True),
        sa.Column("description_raw", sa.String, nullable=False),
        sa.Column("description_normalized", sa.String, nullable=True),
        sa.Column("merchant", sa.String, nullable=True),
        sa.Column("reference", sa.String, nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("transaction_type", sa.String, nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'confirmed'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "transaction_type IN ("
            "'expense', 'income', 'transfer', 'investment', 'dividend', "
            "'interest', 'fee', 'tax', 'refund', 'adjustment'"
            ")",
            name="ck_transactions_transaction_type",
        ),
        sa.CheckConstraint("direction IN ('debit', 'credit')", name="ck_transactions_direction"),
        sa.CheckConstraint("status IN ('pending', 'confirmed')", name="ck_transactions_status"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_transactions_workspace_account",
        ),
    )
    op.create_index("ix_transactions_workspace_id", "transactions", ["workspace_id"])
    op.create_index("ix_transactions_financial_account_id", "transactions", ["financial_account_id"])

    # --- vincolo cross-tenant su category_id (vedi nota in cima al file) -------

    op.execute(
        """
        CREATE FUNCTION check_transaction_category_workspace()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        BEGIN
            IF NEW.category_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM categories
                WHERE id = NEW.category_id
                  AND (workspace_id IS NULL OR workspace_id = NEW.workspace_id)
            ) THEN
                RAISE EXCEPTION
                    'category % does not belong to workspace % or is not a system category',
                    NEW.category_id, NEW.workspace_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "ALTER FUNCTION check_transaction_category_workspace() OWNER TO lumio_rls_helper"
    )
    op.execute(
        """
        CREATE TRIGGER trg_check_transaction_category_workspace
        BEFORE INSERT OR UPDATE OF category_id, workspace_id ON transactions
        FOR EACH ROW EXECUTE FUNCTION check_transaction_category_workspace();
        """
    )

    # --- seed: system categories -----------------------------------------------

    categories_table = sa.table(
        "categories",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("workspace_id", postgresql.UUID(as_uuid=True)),
        sa.column("parent_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("is_system", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        categories_table,
        [
            {
                "id": uuid.UUID(cat["id"]),
                "workspace_id": None,
                "parent_id": uuid.UUID(cat["parent_id"]) if cat["parent_id"] else None,
                "name": cat["name"],
                "code": cat["code"],
                "is_system": True,
                "sort_order": cat["sort_order"],
            }
            for cat in SYSTEM_CATEGORIES_V1
        ],
    )

    # --- Row-Level Security ----------------------------------------------------

    op.execute("ALTER TABLE financial_accounts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE financial_accounts FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY financial_accounts_select ON financial_accounts FOR SELECT
        USING (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY financial_accounts_insert ON financial_accounts FOR INSERT
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY financial_accounts_update ON financial_accounts FOR UPDATE
        USING (is_workspace_member(workspace_id))
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY financial_accounts_delete ON financial_accounts FOR DELETE
        USING (is_workspace_member(workspace_id));
        """
    )

    op.execute("ALTER TABLE categories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE categories FORCE ROW LEVEL SECURITY")
    # BYPASSRLS bypassa le *policy* ma non i normali GRANT (stessa nota di
    # 0002 per workspace_members): lumio_rls_helper deve poter scrivere le
    # system category quando qualcosa fa `SET ROLE lumio_rls_helper` per
    # bypassare intenzionalmente la RLS su queste righe immutabili per
    # l'app (es. il reseed tra i test, vedi tests/conftest.py).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON categories TO lumio_rls_helper")
    # Le categorie di sistema (workspace_id IS NULL) sono visibili a tutti i
    # workspace ma non scrivibili dall'app: nessuna policy INSERT/UPDATE/DELETE
    # le copre (richiedono sempre workspace_id NOT NULL + membership), quindi
    # con FORCE RLS restano di fatto read-only anche per lumio_app.
    op.execute(
        """
        CREATE POLICY categories_select ON categories FOR SELECT
        USING (workspace_id IS NULL OR is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY categories_insert ON categories FOR INSERT
        WITH CHECK (workspace_id IS NOT NULL AND is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY categories_update ON categories FOR UPDATE
        USING (workspace_id IS NOT NULL AND is_workspace_member(workspace_id) AND NOT is_system)
        WITH CHECK (workspace_id IS NOT NULL AND is_workspace_member(workspace_id) AND NOT is_system);
        """
    )
    op.execute(
        """
        CREATE POLICY categories_delete ON categories FOR DELETE
        USING (workspace_id IS NOT NULL AND is_workspace_member(workspace_id) AND NOT is_system);
        """
    )

    op.execute("ALTER TABLE transactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transactions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY transactions_select ON transactions FOR SELECT
        USING (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY transactions_insert ON transactions FOR INSERT
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY transactions_update ON transactions FOR UPDATE
        USING (is_workspace_member(workspace_id))
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY transactions_delete ON transactions FOR DELETE
        USING (is_workspace_member(workspace_id));
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS transactions_delete ON transactions")
    op.execute("DROP POLICY IF EXISTS transactions_update ON transactions")
    op.execute("DROP POLICY IF EXISTS transactions_insert ON transactions")
    op.execute("DROP POLICY IF EXISTS transactions_select ON transactions")

    op.execute("DROP POLICY IF EXISTS categories_delete ON categories")
    op.execute("DROP POLICY IF EXISTS categories_update ON categories")
    op.execute("DROP POLICY IF EXISTS categories_insert ON categories")
    op.execute("DROP POLICY IF EXISTS categories_select ON categories")

    op.execute("DROP POLICY IF EXISTS financial_accounts_delete ON financial_accounts")
    op.execute("DROP POLICY IF EXISTS financial_accounts_update ON financial_accounts")
    op.execute("DROP POLICY IF EXISTS financial_accounts_insert ON financial_accounts")
    op.execute("DROP POLICY IF EXISTS financial_accounts_select ON financial_accounts")

    # Il trigger viene rimosso automaticamente con la tabella; la funzione va
    # eliminata esplicitamente.
    op.drop_table("transactions")
    op.execute("DROP FUNCTION IF EXISTS check_transaction_category_workspace()")
    op.drop_table("categories")
    op.drop_index("ix_financial_accounts_workspace_id", table_name="financial_accounts")
    op.drop_table("financial_accounts")
    op.drop_index("ix_banks_code", table_name="banks")
    op.drop_table("banks")

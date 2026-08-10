"""rules, classifications + RLS

Revision ID: 0006_rules_classifications
Revises: 0005_bank_parsers
Create Date: 2026-08-10

Milestone 06 — Rules Engine (SPEC §23, §24).

`rules' e' tenant-scoped come `financial_accounts` (workspace_id diretto,
stesso pattern RLS a 4 policy). `category_id` e' NOT NULL e punta a
`categories.id` con una FK semplice (non composita): come per
`transactions.category_id` in 0003, puo' riferire sia una categoria del
proprio workspace sia una categoria di sistema (workspace_id NULL), quindi
una FK composita non e' applicabile e la RLS da sola non basta (Postgres non
applica la RLS della tabella referenziata quando verifica un vincolo FK).
Riusiamo lo stesso trigger `check_transaction_category_workspace` creato in
0003_accounts_transactions: la funzione legge solo `NEW.category_id` e
`NEW.workspace_id`, generica per qualunque tabella con quelle due colonne —
nessuna nuova funzione necessaria per `rules`.

`classifications' e' uno storico append-only (SPEC §24) collegato a
`transactions`, SENZA una colonna `workspace_id` diretta (lo schema SPEC non
la elenca, a differenza di `imports`/`transactions` dove invece compare
esplicitamente — scelta rispettata: il tenant scoping avviene via join a
`transactions`). Questo significa che il trigger di 0003 non e' riusabile
cosi' com'e' (si aspetta NEW.workspace_id direttamente): serve una nuova
funzione `check_classification_category_workspace` che risolve il workspace
della transazione con una query. La RLS segue lo stesso principio con una
policy EXISTS invece del confronto diretto su una colonna. Nessuna policy
UPDATE/DELETE: con FORCE ROW LEVEL SECURITY questo nega di default entrambe
le operazioni per `lumio_app` — lo storico e' immutabile per design, stesso
pattern gia' usato per le system category in 0003 (nessuna policy
INSERT/UPDATE/DELETE per workspace_id IS NULL le rende di fatto read-only).

Deviazioni minori documentate dallo schema SPEC letterale (vedi anche i
commenti nei modelli): `classifications` non ha `subcategory_id` (ridondante
con la gerarchia `categories.parent_id` gia' costruita in M03) ma ha
`created_by_user_id` (assente da SPEC §24, necessario per il DoD "chi ha
classificato" — stesso precedente di `imports.created_by_user_id` in M04).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_rules_classifications"
down_revision: Union[str, None] = "0005_bank_parsers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- rules -----------------------------------------------------------------

    op.create_table(
        "rules",
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
        sa.Column("field", sa.String, nullable=False),
        sa.Column("operator", sa.String, nullable=False),
        sa.Column("value", sa.String, nullable=False),
        sa.Column(
            "category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=False
        ),
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("100")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("field IN ('description', 'merchant')", name="ck_rules_field"),
        sa.CheckConstraint(
            "operator IN ('equals', 'contains', 'starts_with', 'ends_with', 'regex', 'merchant_equals')",
            name="ck_rules_operator",
        ),
    )
    op.create_index("ix_rules_workspace_id", "rules", ["workspace_id"])

    op.execute(
        """
        CREATE TRIGGER trg_check_rules_category_workspace
        BEFORE INSERT OR UPDATE OF category_id, workspace_id ON rules
        FOR EACH ROW EXECUTE FUNCTION check_transaction_category_workspace();
        """
    )

    op.execute("ALTER TABLE rules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rules FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rules_select ON rules FOR SELECT
        USING (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY rules_insert ON rules FOR INSERT
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY rules_update ON rules FOR UPDATE
        USING (is_workspace_member(workspace_id))
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY rules_delete ON rules FOR DELETE
        USING (is_workspace_member(workspace_id));
        """
    )

    # --- classifications ---------------------------------------------------------

    op.create_table(
        "classifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String, nullable=False),
        sa.Column("provider", sa.String, nullable=True),
        sa.Column("model", sa.String, nullable=True),
        sa.Column(
            "category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True
        ),
        sa.Column("score", sa.Numeric(3, 2), nullable=True),
        sa.Column("explanation", sa.String, nullable=True),
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "method IN ('rule', 'ai', 'user', 'manual', 'system')", name="ck_classifications_method"
        ),
    )
    op.create_index("ix_classifications_transaction_id", "classifications", ["transaction_id"])

    # SECURITY DEFINER esegue come lumio_rls_helper (BYPASSRLS): bypassa le
    # *policy* di transactions/categories ma non i normali privilegi (stessa
    # nota gia' valida per categories in 0003) — serve un GRANT esplicito su
    # transactions, non ancora concesso da nessuna migration precedente
    # (0003 concede solo su categories, l'unica tabella che
    # check_transaction_category_workspace interroga).
    op.execute("GRANT SELECT ON transactions TO lumio_rls_helper")

    op.execute(
        """
        CREATE FUNCTION check_classification_category_workspace()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        DECLARE
            txn_workspace_id uuid;
        BEGIN
            SELECT workspace_id INTO txn_workspace_id FROM transactions WHERE id = NEW.transaction_id;
            IF NEW.category_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM categories
                WHERE id = NEW.category_id
                  AND (workspace_id IS NULL OR workspace_id = txn_workspace_id)
            ) THEN
                RAISE EXCEPTION
                    'category % does not belong to workspace of transaction %',
                    NEW.category_id, NEW.transaction_id
                    USING ERRCODE = 'foreign_key_violation';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "ALTER FUNCTION check_classification_category_workspace() OWNER TO lumio_rls_helper"
    )
    op.execute(
        """
        CREATE TRIGGER trg_check_classification_category_workspace
        BEFORE INSERT OR UPDATE OF category_id, transaction_id ON classifications
        FOR EACH ROW EXECUTE FUNCTION check_classification_category_workspace();
        """
    )

    op.execute("ALTER TABLE classifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE classifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY classifications_select ON classifications FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM transactions t
                WHERE t.id = classifications.transaction_id AND is_workspace_member(t.workspace_id)
            )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY classifications_insert ON classifications FOR INSERT
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM transactions t
                WHERE t.id = classifications.transaction_id AND is_workspace_member(t.workspace_id)
            )
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS classifications_insert ON classifications")
    op.execute("DROP POLICY IF EXISTS classifications_select ON classifications")
    op.drop_table("classifications")
    op.execute("DROP FUNCTION IF EXISTS check_classification_category_workspace()")
    op.execute("REVOKE SELECT ON transactions FROM lumio_rls_helper")

    op.execute("DROP POLICY IF EXISTS rules_delete ON rules")
    op.execute("DROP POLICY IF EXISTS rules_update ON rules")
    op.execute("DROP POLICY IF EXISTS rules_insert ON rules")
    op.execute("DROP POLICY IF EXISTS rules_select ON rules")
    op.drop_index("ix_rules_workspace_id", table_name="rules")
    op.drop_table("rules")

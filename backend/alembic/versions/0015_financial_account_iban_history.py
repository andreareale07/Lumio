"""financial_account_iban_history + RLS

Revision ID: 0015_iban_history
Revises: 0014_workspace_members_grant
Create Date: 2026-08-11

Milestone 09.5c: caso reale trovato dall'utente — un istituto (Trade
Republic) puo' cambiare l'IBAN di un conto pur restando lo stesso conto
(migrazione DE -> IT osservata dall'utente); gli estratti conto passati
riportano ancora il VECCHIO IBAN come controparte dei bonifici. Se il
riconoscimento (`app/services/transfer_recognition.py`) controllasse solo
`financial_accounts.iban` (il valore ATTUALE), quei bonifici storici non
verrebbero mai riconosciuti come interni.

Storicizzazione AUTOMATICA (nessuna lista da compilare a mano): quando
l'utente cambia l'IBAN di un conto (`PATCH /accounts/{id}`), il valore
PRECEDENTE viene salvato qui prima di essere sovrascritto — vedi
`app/api/v1/accounts.py`. Il riconoscimento controlla poi TUTTI gli IBAN
mai appartenuti a un conto del workspace, non solo quello attuale.

Stesso pattern RLS standard di `0009`/`0010`/`0011`/`0012`.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_iban_history"
down_revision: Union[str, None] = "0014_workspace_members_grant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_account_iban_history",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iban", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "workspace_id", "financial_account_id", "iban", name="uq_iban_history_account_iban"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_iban_history_workspace_account",
        ),
    )
    op.create_index(
        "ix_iban_history_workspace_id", "financial_account_iban_history", ["workspace_id"]
    )
    op.create_index(
        "ix_iban_history_account_id", "financial_account_iban_history", ["financial_account_id"]
    )

    op.execute("ALTER TABLE financial_account_iban_history ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE financial_account_iban_history FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY financial_account_iban_history_select ON financial_account_iban_history "
        "FOR SELECT USING (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY financial_account_iban_history_insert ON financial_account_iban_history "
        "FOR INSERT WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY financial_account_iban_history_update ON financial_account_iban_history "
        "FOR UPDATE USING (is_workspace_member(workspace_id)) "
        "WITH CHECK (is_workspace_member(workspace_id));"
    )
    op.execute(
        "CREATE POLICY financial_account_iban_history_delete ON financial_account_iban_history "
        "FOR DELETE USING (is_workspace_member(workspace_id));"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS financial_account_iban_history_delete ON financial_account_iban_history"
    )
    op.execute(
        "DROP POLICY IF EXISTS financial_account_iban_history_update ON financial_account_iban_history"
    )
    op.execute(
        "DROP POLICY IF EXISTS financial_account_iban_history_insert ON financial_account_iban_history"
    )
    op.execute(
        "DROP POLICY IF EXISTS financial_account_iban_history_select ON financial_account_iban_history"
    )
    op.drop_index("ix_iban_history_account_id", table_name="financial_account_iban_history")
    op.drop_index("ix_iban_history_workspace_id", table_name="financial_account_iban_history")
    op.drop_table("financial_account_iban_history")

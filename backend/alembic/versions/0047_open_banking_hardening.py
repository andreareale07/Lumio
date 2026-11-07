"""open banking: cursore recuperabile, tombstone, statistiche di sync, REVIEW non riaccodate

Revision ID: 0047_open_banking_hardening
Revises: 0046_push_devices
Create Date: 2026-11-07

- `bank_connection_accounts.last_sync_stats` (JSONB): solo conteggi per la
  diagnostica, mai causali, importi o nomi.
- `bank_connection_accounts.balance_snapshot` (JSONB): ultimo saldo dichiarato
  dalla banca + esito del controllo di continuita' su `balance_after`.
- `transaction_review_items.external_id`: la sync non riaccoda le righe che
  hanno gia' una review (pendente o decisa) per quell'id della banca.
- `bank_transaction_tombstones`: id banca di movimenti eliminati a mano, cosi'
  la finestra di sovrapposizione non li riporta indietro. RLS di workspace.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_open_banking_hardening"
down_revision: Union[str, None] = "0046_push_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "bank_transaction_tombstones"
_MEMBER = "is_workspace_member(workspace_id)"


def upgrade() -> None:
    op.add_column("bank_connection_accounts", sa.Column("last_sync_stats", postgresql.JSONB, nullable=True))
    op.add_column("bank_connection_accounts", sa.Column("balance_snapshot", postgresql.JSONB, nullable=True))

    op.add_column("transaction_review_items", sa.Column("external_id", sa.String, nullable=True))
    op.execute(
        "CREATE INDEX ix_transaction_review_items_account_external_id "
        "ON transaction_review_items (workspace_id, financial_account_id, external_id) "
        "WHERE external_id IS NOT NULL"
    )

    op.create_table(
        _TABLE,
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_bank_transaction_tombstones_workspace_account",
        ),
        sa.UniqueConstraint("financial_account_id", "external_id", name="uq_bank_transaction_tombstones_account_ext"),
    )
    op.create_index("ix_bank_transaction_tombstones_workspace_id", _TABLE, ["workspace_id"])
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {_TABLE}_select ON {_TABLE} FOR SELECT USING ({_MEMBER})")
    op.execute(f"CREATE POLICY {_TABLE}_insert ON {_TABLE} FOR INSERT WITH CHECK ({_MEMBER})")
    op.execute(f"CREATE POLICY {_TABLE}_update ON {_TABLE} FOR UPDATE USING ({_MEMBER}) WITH CHECK ({_MEMBER})")
    op.execute(f"CREATE POLICY {_TABLE}_delete ON {_TABLE} FOR DELETE USING ({_MEMBER})")


def downgrade() -> None:
    for policy in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS {_TABLE}_{policy} ON {_TABLE}")
    op.drop_table(_TABLE)
    op.execute("DROP INDEX IF EXISTS ix_transaction_review_items_account_external_id")
    op.drop_column("transaction_review_items", "external_id")
    op.drop_column("bank_connection_accounts", "balance_snapshot")
    op.drop_column("bank_connection_accounts", "last_sync_stats")

"""Override per singolo evento realizzato (FETTA 2)

Revision ID: 0040_tax_event_overrides
Revises: 0039_tax_domain
Create Date: 2026-09-05

`tax_realized_event_overrides`: riga presente SOLO se l'utente corregge un
evento realizzato calcolato dal motore a lotti (es. costo di carico storico
sbagliato) — l'assenza di riga significa "usa il valore calcolato", stesso
principio di `asset_tax_classifications` (0039).

Un evento e' identificato dalla coppia `(lot_transaction_id,
sell_transaction_id)`, univoca per costruzione (il motore consuma un dato
lotto al massimo una volta per vendita) — FK composite verso
`investment_transactions` su ENTRAMBE le colonne, per garanzia referenziale
reale (mai un override "orfano" su una transazione cancellata).

RLS: stesso pattern delle 4 tabelle di 0039 (ENABLE + FORCE, 4 policy
separate con `is_workspace_member`).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0040_tax_event_overrides"
down_revision: Union[str, None] = "0039_tax_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "tax_realized_event_overrides"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sell_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("override_gain_or_loss", sa.Numeric(18, 2), nullable=True),
        sa.Column("excluded", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["workspace_id", "lot_transaction_id"],
            ["investment_transactions.workspace_id", "investment_transactions.id"],
            ondelete="CASCADE",
            name="fk_tax_realized_event_overrides_workspace_lot_transaction",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "sell_transaction_id"],
            ["investment_transactions.workspace_id", "investment_transactions.id"],
            ondelete="CASCADE",
            name="fk_tax_realized_event_overrides_workspace_sell_transaction",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "lot_transaction_id",
            "sell_transaction_id",
            name="uq_tax_realized_event_overrides_event",
        ),
    )
    op.create_index(f"ix_{_TABLE}_workspace_id", _TABLE, ["workspace_id"])
    op.create_index(f"ix_{_TABLE}_lot_transaction_id", _TABLE, ["lot_transaction_id"])
    op.create_index(f"ix_{_TABLE}_sell_transaction_id", _TABLE, ["sell_transaction_id"])

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_select ON {_TABLE} FOR SELECT
        USING (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_insert ON {_TABLE} FOR INSERT
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_update ON {_TABLE} FOR UPDATE
        USING (is_workspace_member(workspace_id))
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_delete ON {_TABLE} FOR DELETE
        USING (is_workspace_member(workspace_id));
        """
    )


def downgrade() -> None:
    for policy in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS {_TABLE}_{policy} ON {_TABLE}")
    op.drop_table(_TABLE)

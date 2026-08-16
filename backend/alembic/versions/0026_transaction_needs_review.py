"""transactions: needs_review + soglia configurabile

Revision ID: 0026_transaction_needs_review
Revises: 0025_reclassification_job
Create Date: 2026-08-16

Rework pipeline di classificazione (SPEC §43, "319 classificati, 8 da
verificare"). `needs_review` e' scritta SOLO da chi produce una
`Classification` con uno `score` (confrontato con la soglia qui seminata)
e azzerata da `update_transaction` alla correzione manuale — mai calcolata
a runtime da una query (vedi app/services/confidence.py:needs_review).

`server_default='false'` rende l'`ADD COLUMN NOT NULL` istantaneo su
tabella popolata, stesso pattern di `kind` in 0021. Nessun bypass RLS
necessario: e' DDL (ALTER TABLE), non una scrittura riga per riga.

Soglia in `system_settings`, non in `config.py`: aggiustabile senza
riavviare il worker (stesso motivo delle soglie di stallo job_health).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0026_transaction_needs_review"
down_revision: Union[str, None] = "0025_reclassification_job"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_settings_table = sa.table(
    "system_settings",
    sa.column("key", sa.String),
    sa.column("value", postgresql.JSONB),
    sa.column("default_value", postgresql.JSONB),
    sa.column("description", sa.String),
)


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.bulk_insert(
        _settings_table,
        [
            {
                "key": "classification.needs_review_threshold",
                "value": 0.6,
                "default_value": 0.6,
                "description": (
                    "Sotto questo punteggio di confidence, una transazione classificata viene "
                    "marcata 'da verificare' invece di essere considerata risolta."
                ),
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key = 'classification.needs_review_threshold'")
    op.drop_column("transactions", "needs_review")

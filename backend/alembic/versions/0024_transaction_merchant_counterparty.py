"""transactions: counterparty_name/counterparty_iban + indice su merchant

Revision ID: 0024_transaction_counterparty
Revises: 0023_ai_classification_error
Create Date: 2026-08-16

Rework pipeline di classificazione. `merchant` esiste dalla migration 0003
ma non e' mai stato popolato da nessun parser — questa migration NON tocca
quella colonna (nessun cambio di schema necessario), solo aggiunge
`counterparty_name`/`counterparty_iban` (nome/IBAN della controparte di un
bonifico, oggi estratti a runtime da `transfer_recognition.py` e scartati
subito dopo il check di trasferimento interno).

Nessun indice su `(workspace_id, merchant)` da aggiungere qui: esiste gia'
(`ix_transactions_workspace_merchant`, creato da `0008_analytics_indexes.py`
in previsione esplicita di questo momento) — con `merchant` finalmente
popolato dal rework, quell'indice smette di essere decorativo e il GROUP BY
di `by_merchant` (`app/services/analytics.py`) diventa effettivamente
selettivo.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_transaction_counterparty"
down_revision: Union[str, None] = "0023_ai_classification_error"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("counterparty_name", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("counterparty_iban", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "counterparty_iban")
    op.drop_column("transactions", "counterparty_name")

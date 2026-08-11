"""indici compositi su transactions per analytics

Revision ID: 0008_analytics_indexes
Revises: 0007_ai_settings
Create Date: 2026-08-11

Milestone 08 — Dashboard + Analytics (SPEC §30, 39, 45, 46, 73, 74).

Nessuna tabella nuova, quindi nessuna policy RLS da scrivere. Gli endpoint
`/api/v1/analytics/*` introdotti in questa milestone aggregano `transactions`
per periodo, conto, categoria, tipo e merchant: oggi la tabella ha solo tre
indici a colonna singola (`workspace_id`, `financial_account_id`,
`import_id`, vedi 0003/0004) e nessun indice su `category_id` (Postgres non
indicizza automaticamente le colonne FK). In un workspace singolo
`workspace_id` da solo ha selettivita' ~1, quindi ogni filtro per periodo
farebbe seq scan sull'intera tabella — inaccettabile per il DoD della
milestone ("dashboard carica in tempo utile con migliaia di transazioni").

Ogni indice ha `workspace_id` come colonna guida (a sinistra) per restare
utile sotto RLS e coerente con "mai fidarsi solo della RLS" (CLAUDE.md): la
query applicativa filtra sempre esplicitamente su `workspace_id` prima di
qualunque altro filtro.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_analytics_indexes"
down_revision: Union[str, None] = "0007_ai_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_workspace_date",
        "transactions",
        ["workspace_id", "transaction_date"],
    )
    op.create_index(
        "ix_transactions_workspace_account_date",
        "transactions",
        ["workspace_id", "financial_account_id", "transaction_date"],
    )
    op.create_index(
        "ix_transactions_workspace_category_date",
        "transactions",
        ["workspace_id", "category_id", "transaction_date"],
    )
    op.create_index(
        "ix_transactions_workspace_type_date",
        "transactions",
        ["workspace_id", "transaction_type", "transaction_date"],
    )
    op.create_index(
        "ix_transactions_workspace_merchant",
        "transactions",
        ["workspace_id", "merchant"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_workspace_merchant", table_name="transactions")
    op.drop_index("ix_transactions_workspace_type_date", table_name="transactions")
    op.drop_index("ix_transactions_workspace_category_date", table_name="transactions")
    op.drop_index("ix_transactions_workspace_account_date", table_name="transactions")
    op.drop_index("ix_transactions_workspace_date", table_name="transactions")

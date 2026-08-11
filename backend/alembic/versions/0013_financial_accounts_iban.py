"""financial_accounts.iban

Revision ID: 0013_financial_accounts_iban
Revises: 0012_transaction_type_mappings
Create Date: 2026-08-11

Milestone 09.5b — riconoscimento automatico dei trasferimenti interni
(SPEC §37 "escludere correttamente i trasferimenti interni"): l'IBAN del
conto e' il segnale piu' affidabile (niente falsi positivi da omonimia,
a differenza del solo nominativo) per riconoscere se la controparte di un
bonifico e' un conto proprio del workspace. Nullable, editabile in
creazione e modifica conto — nessun backfill possibile sui conti gia'
esistenti, l'utente lo aggiunge quando vuole.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_financial_accounts_iban"
down_revision: Union[str, None] = "0012_transaction_type_mappings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("financial_accounts", sa.Column("iban", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("financial_accounts", "iban")

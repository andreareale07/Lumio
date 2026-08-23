"""financial_accounts.classification_language

Revision ID: 0034_account_classify_lang
Revises: 0033_transaction_dedup
Create Date: 2026-08-23

Fetta 2 di PLAN_TAXONOMY_I18N.md: lingua usata nel testo delle categorie di
sistema offerte al modello AI durante la classificazione delle transazioni
di questo conto (es. un conto estero con estratto conto in inglese),
indipendente dalla lingua della UI. Nullable, NULL = italiano (default,
comportamento invariato per i conti esistenti). Mai influenza le categorie
utente ne' description_raw della transazione.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034_account_classify_lang"
down_revision: Union[str, None] = "0033_transaction_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("financial_accounts", sa.Column("classification_language", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_financial_accounts_classification_language",
        "financial_accounts",
        "classification_language IN ('it', 'en') OR classification_language IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_financial_accounts_classification_language", "financial_accounts", type_="check")
    op.drop_column("financial_accounts", "classification_language")

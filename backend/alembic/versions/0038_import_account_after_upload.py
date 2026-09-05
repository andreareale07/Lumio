"""imports.financial_account_id nullable: il conto si sceglie DOPO l'upload

Revision ID: 0038_import_account_after_upload
Revises: 0037_market_data_live_quotes
Create Date: 2026-08-29

Il flusso di import passa da "scegli il conto prima di caricare" a "carica,
poi conferma/crea il conto" (matching IBAN/storico IBAN estratto dal
documento quando disponibile — vedi app/services/account_matching.py). La
riga `imports` puo' quindi esistere per un breve periodo (stato 'uploaded')
senza un conto ancora assegnato, valorizzato da un nuovo endpoint dedicato
(`POST /imports/{id}/resolve-account`) prima della conferma vera e propria.

La FK composita `(workspace_id, financial_account_id)` verso
`financial_accounts` (vedi 0004_imports.py) resta valida con NULL: Postgres
non valuta un FK composito quando una colonna e' NULL (MATCH SIMPLE,
default) — nessuna modifica al vincolo stesso, nessun impatto RLS (le
policy sono su workspace_id, mai su questa colonna).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0038_import_account_after_upload"
down_revision: Union[str, None] = "0037_market_data_live_quotes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("imports", "financial_account_id", nullable=True)


def downgrade() -> None:
    op.alter_column("imports", "financial_account_id", nullable=False)

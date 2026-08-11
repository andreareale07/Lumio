"""grant INSERT su workspace_members a lumio_rls_helper

Revision ID: 0014_workspace_members_grant
Revises: 0013_financial_accounts_iban
Create Date: 2026-08-11

`lumio_rls_helper` aveva gia' SELECT su `workspace_members` (migration
0002, serve alla funzione SECURITY DEFINER `is_workspace_member`) ma non
INSERT — BYPASSRLS bypassa le *policy* ma non i normali GRANT (stessa nota
gia' presente su `categories`, migration 0003). Senza INSERT, un test che
debba simulare un workspace con piu' membri (SPEC: workspace familiare,
l'app non ha ancora un flusso di invito reale) non ha modo di inserire la
riga di appartenenza di un secondo utente sotto `SET ROLE lumio_rls_helper`
— l'unico bypass disponibile, stesso principio del reseed delle system
category in `tests/conftest.py`. Nessun path applicativo usa questo
bypass (CLAUDE.md: mai `SET ROLE lumio_rls_helper` nel codice dell'app).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_workspace_members_grant"
down_revision: Union[str, None] = "0013_financial_accounts_iban"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("GRANT INSERT ON workspace_members TO lumio_rls_helper")


def downgrade() -> None:
    op.execute("REVOKE INSERT ON workspace_members FROM lumio_rls_helper")

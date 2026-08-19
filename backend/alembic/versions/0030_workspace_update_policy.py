"""workspaces: policy RLS di UPDATE (solo owner) — sistema di valute

Revision ID: 0030_workspace_update_policy
Revises: 0029_currencies
Create Date: 2026-08-17

Gap reale scoperto implementando `PATCH /workspace` (sistema di valute,
per cambiare `base_currency`): la migration 0002 aveva deliberatamente
lasciato `workspaces` senza nessuna policy UPDATE/DELETE ("nessun endpoint
li usa ancora in questa milestone", commento originale) — con `FORCE ROW
LEVEL SECURITY` gia' attivo, questo significa che OGNI UPDATE su
`workspaces` viene negato di default, in silenzio (0 righe aggiornate,
nessun errore). Riusa `is_workspace_owner()` (gia' definita in migration
0002 per il bootstrap di `workspace_members`) — stessa restrizione "solo
owner" gia' applicata a `workspaces_insert`, non estesa a tutti i membri:
le impostazioni del workspace (oggi solo `base_currency`) restano una
decisione del proprietario, coerente con `owner_user_id` come unico
concetto di ruolo esistente nel modello (nessun ruolo admin/membro separato
ancora implementato).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_workspace_update_policy"
down_revision: Union[str, None] = "0029_currencies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY workspaces_update ON workspaces FOR UPDATE
        USING (is_workspace_owner(id))
        WITH CHECK (is_workspace_owner(id));
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workspaces_update ON workspaces")

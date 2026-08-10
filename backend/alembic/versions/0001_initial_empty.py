"""initial empty migration

Revision ID: 0001_initial_empty
Revises:
Create Date: 2026-08-10

Migration vuota di verifica: conferma che Alembic e' collegato correttamente
al database configurato tramite DATABASE_URL (milestone 01 — Foundation, DoD).
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001_initial_empty"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

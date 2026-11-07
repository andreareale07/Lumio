"""2FA TOTP opzionale: colonne su users

Revision ID: 0045_totp_2fa
Revises: 0044_open_banking
Create Date: 2026-11-07

`users` non ha RLS (tabella di lookup del login), quindi nessuna policy da
aggiungere: il segreto TOTP e' cifrato a riposo e mai esposto dalle API.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045_totp_2fa"
down_revision: Union[str, None] = "0044_open_banking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret_encrypted")

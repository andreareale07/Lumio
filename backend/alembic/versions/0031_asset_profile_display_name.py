"""asset_profiles.display_name — nome pulito del titolo dal provider

Revision ID: 0031_asset_profile_display_name
Revises: 0030_workspace_update_policy
Create Date: 2026-08-17

Il parser Trade Republic estrae il nome asset verbatim dal PDF (SPEC M09c,
`app/services/trade_parsing.py`), che include spesso la notazione tedesca
di borsa per il valore nominale ("DL-,0001" = dollari, "EO-,01" = euro,
"DK 0,1" = corone danesi) e talvolta refusi del broker stesso (es.
"QUATUM" invece di "Quantum"). Invece di ripulire il nome grezzo con
un'euristica fragile, si riusa l'arricchimento gia' costruito nello Step 3
(`fetch_profile`, quoteSummary di Yahoo) per offrire un nome alternativo
"pulito" (`quoteType.longName`) — MAI una sovrascrittura di `Asset.name`
(che resta il dato cosi' come importato), solo un campo opzionale in piu'
nella stessa cache best-effort gia' esistente.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_asset_profile_display_name"
down_revision: Union[str, None] = "0030_workspace_update_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("asset_profiles", sa.Column("display_name", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("asset_profiles", "display_name")

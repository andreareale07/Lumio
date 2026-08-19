"""asset_prices.updated_at — traccia l'ultimo refresh, non solo l'inserimento

Revision ID: 0032_asset_prices_updated_at
Revises: 0031_asset_profile_display_name
Create Date: 2026-08-18

`created_at` non veniva mai toccato da un upsert successivo (fetch/salvataggio
di un prezzo gia' presente per lo stesso giorno) — restava congelato alla
primissima scrittura, quindi non poteva dire "quando abbiamo controllato
l'ultima volta questo prezzo". Serve per la cache-first di `GET /assets/{id}
/price-history` (evitare di richiamare Yahoo a ogni cambio di range quando
il dato di oggi e' gia' stato scaricato di recente, entro una finestra di
15 minuti — SPEC discussione utente su rischio 429/999).

Backfill: `updated_at = created_at` per le righe esistenti (nessuna riga
sarebbe considerata "appena aggiornata" con un default a `now()`, il che
forzerebbe un refresh live per TUTTO lo storico gia' scaricato alla prima
richiesta dopo la migration — un default a `created_at` mantiene lo stato
"non aggiornato di recente" per i dati vecchi, senza inventare una
freschezza che non c'e' mai stata).

La colonna nasce GIA' con un default a livello DB (`now()`), non solo
lato ORM: eseguita su produzione con l'app/worker gia' in esecuzione, un
`INSERT` concorrente (es. il refresh prezzi del worker) tra l'`ADD COLUMN`
e l'`UPDATE` di backfill prenderebbe altrimenti `NULL` per la nuova
colonna (nessun default DB ancora presente in quella finestra), facendo
fallire il passaggio successivo a `NOT NULL` con una `NotNullViolationError`
— bug reale osservato eseguendo questa stessa migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_asset_prices_updated_at"
down_revision: Union[str, None] = "0031_asset_profile_display_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "asset_prices",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    )
    op.execute("UPDATE asset_prices SET updated_at = created_at")
    op.alter_column("asset_prices", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("asset_prices", "updated_at")

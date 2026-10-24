"""job_runs: job_kind "positions_recompute" + colonna `details` (resoconto)

Revision ID: 0041_positions_recompute_job
Revises: 0040_tax_event_overrides
Create Date: 2026-10-24

Ricalcolo manuale delle posizioni dai movimenti (Impostazioni > Manutenzione):
`positions` e' un valore salvato che si aggiorna solo quando un suo movimento
cambia, quindi dopo una correzione al calcolo i valori gia' salvati restano
quelli vecchi. Il job e' lanciabile da UI e lascia un resoconto di COSA ha
modificato in `job_runs.details` (JSONB, nullable, sovrascritto a ogni
esecuzione come il resto della riga) — il log del worker non e' consultabile
dall'utente, il resoconto si'.

Stesso pattern di `0036_snapshot_backfill_job.py` per allargare
`ck_job_runs_job_kind` e seminare la soglia di job_health.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_positions_recompute_job"
down_revision: Union[str, None] = "0040_tax_event_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_JOB_KINDS = (
    "market_data_refresh",
    "snapshot_rebuild",
    "google_sheets_export",
    "reclassification",
    "snapshot_backfill",
)
_NEW_JOB_KINDS = _OLD_JOB_KINDS + ("positions_recompute",)

_settings_table = sa.table(
    "system_settings",
    sa.column("key", sa.String),
    sa.column("value", postgresql.JSONB),
    sa.column("default_value", postgresql.JSONB),
    sa.column("description", sa.String),
)


def upgrade() -> None:
    op.add_column("job_runs", sa.Column("details", postgresql.JSONB, nullable=True))
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        "CHECK (job_kind IN (" + ", ".join(f"'{k}'" for k in _NEW_JOB_KINDS) + "))"
    )
    op.bulk_insert(
        _settings_table,
        [
            {
                "key": "job_health.positions_recompute.stale_after_seconds",
                "value": 1800,
                "default_value": 1800,
                "description": (
                    "Ricalcolo posizioni: dopo quanti secondi dall'avvio "
                    "un'esecuzione ancora 'running' e' considerata bloccata."
                ),
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key = 'job_health.positions_recompute.stale_after_seconds'")
    # `job_runs` ha la RLS FORZATA: senza un'identita' di workspace un DELETE
    # dell'utente della migration non vede nessuna riga. La si sospende solo per
    # il tempo della pulizia e si ripristina subito (stessa transazione).
    op.execute("ALTER TABLE job_runs NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM job_runs WHERE job_kind = 'positions_recompute'")
    op.execute("ALTER TABLE job_runs FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        "CHECK (job_kind IN (" + ", ".join(f"'{k}'" for k in _OLD_JOB_KINDS) + "))"
    )
    op.drop_column("job_runs", "details")

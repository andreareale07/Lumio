"""job_runs: aggiunge il job_kind "snapshot_backfill"

Revision ID: 0036_snapshot_backfill_job
Revises: 0035_detection_overrides
Create Date: 2026-08-25

FETTA 3 (storico patrimonio ricostruito): nuovo job triggerabile
automaticamente a fine import e manualmente da
`POST /portfolios/snapshots/backfill`, che ricostruisce
`net_worth_snapshots`/`portfolio_snapshots` (aggregato) per ogni giorno di
un intervallo storico — a differenza di `snapshot_rebuild` (cron/trigger
manuale del SOLO giorno odierno), che resta invariato.

NOTA sulla numerazione: la revision "0035" (fetta ricorrenze/anomalie,
`detection_overrides`, sviluppata in parallelo in un'altra sessione) e'
stata scritta indipendentemente da questa, entrambe puntando in origine a
"0034_account_classify_lang" — corretto qui in fase di unione a
"0035_detection_overrides" per mantenere una catena lineare invece di due
head. Le due migration non toccano oggetti in comune (0035 crea solo la
tabella `detection_overrides` + RLS, questa allarga `ck_job_runs_job_kind`
e semina un system setting), quindi l'ordine fra le due non e' significativo
di per se' — serve solo a evitare due head divergenti in Alembic.

Stesso pattern gia' usato per allargare `ck_job_runs_job_kind` in
`0025_reclassification_job.py` (che a sua volta lo cita come gia' usato per
"google_sheets_export" in 0016): un valore nuovo richiede sempre di
allargare il CHECK qui, non solo `JOB_KINDS` in models/job_run.py.

**Non tocca** `ck_audit_log_event_type` (il backfill non logga un evento di
audit finanziario, stesso principio di `snapshot_rebuild`, che non ne logga
uno neppure lui) ne' aggiunge colonne/indici — la sola query aggiuntiva
(`transactions(workspace_id, financial_account_id, transaction_date)`) e'
gia' coperta dagli indici esistenti (`0008_analytics_indexes.py`).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0036_snapshot_backfill_job"
down_revision: Union[str, None] = "0035_detection_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_JOB_KINDS = ("market_data_refresh", "snapshot_rebuild", "google_sheets_export", "reclassification")
_NEW_JOB_KINDS = _OLD_JOB_KINDS + ("snapshot_backfill",)

_settings_table = sa.table(
    "system_settings",
    sa.column("key", sa.String),
    sa.column("value", postgresql.JSONB),
    sa.column("default_value", postgresql.JSONB),
    sa.column("description", sa.String),
)


def upgrade() -> None:
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        "CHECK (job_kind IN (" + ", ".join(f"'{k}'" for k in _NEW_JOB_KINDS) + "))"
    )

    op.bulk_insert(
        _settings_table,
        [
            {
                "key": "job_health.snapshot_backfill.stale_after_seconds",
                "value": 3600,
                "default_value": 3600,
                "description": (
                    "Storico patrimonio ricostruito: dopo quanti secondi dall'avvio "
                    "un'esecuzione ancora 'running' e' considerata bloccata."
                ),
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key = 'job_health.snapshot_backfill.stale_after_seconds'")

    # Un job_run 'snapshot_backfill' esistente farebbe fallire il DROP+ADD
    # del CHECK piu' ristretto sotto — stessa cura richiesta esplicitamente
    # dal piano (§3.8): rimuovere le righe prima di ripristinare il vincolo.
    op.execute("DELETE FROM job_runs WHERE job_kind = 'snapshot_backfill'")

    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        "CHECK (job_kind IN (" + ", ".join(f"'{k}'" for k in _OLD_JOB_KINDS) + "))"
    )

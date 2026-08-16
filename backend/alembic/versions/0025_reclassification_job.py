"""job_runs/audit_log: aggiunge il job_kind/event_type "reclassification"

Revision ID: 0025_reclassification_job
Revises: 0024_transaction_counterparty
Create Date: 2026-08-16

Rework pipeline di classificazione: nuovo job triggerabile manualmente che
riapplica la pipeline (regole utente -> sistema -> opzionalmente AI) alle
transazioni gia' importate, senza reimportare — necessario perche' la
tassonomia e' cambiata (0021/0022) dopo che l'utente aveva gia' classificato
mesi di storico con quella vecchia.

Stesso pattern gia' usato per aggiungere "google_sheets_export" a JOB_KINDS
(0016) e "IMPORT_DELETED" a EVENT_TYPES (0018): entrambi sono CHECK
constraint chiusi, un valore nuovo richiede sempre di allargarli qui, non
solo nei rispettivi moduli Python.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0025_reclassification_job"
down_revision: Union[str, None] = "0024_transaction_counterparty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_JOB_KINDS = ("market_data_refresh", "snapshot_rebuild", "google_sheets_export")
_NEW_JOB_KINDS = _OLD_JOB_KINDS + ("reclassification",)

_OLD_EVENT_TYPES = (
    "LOGIN",
    "IMPORT_CREATED",
    "IMPORT_COMPLETED",
    "TRANSACTION_UPDATED",
    "CATEGORY_CHANGED",
    "RULE_CREATED",
    "RULE_UPDATED",
    "AI_PROVIDER_CHANGED",
    "GOOGLE_CONNECTED",
    "EXPORT_CREATED",
    "IMPORT_DELETED",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("RECLASSIFICATION_RUN",)

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

    op.execute("ALTER TABLE audit_log DROP CONSTRAINT ck_audit_log_event_type")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_event_type "
        "CHECK (event_type IN (" + ", ".join(f"'{e}'" for e in _NEW_EVENT_TYPES) + "))"
    )

    op.bulk_insert(
        _settings_table,
        [
            {
                "key": "job_health.reclassification.stale_after_seconds",
                "value": 420,
                "default_value": 420,
                "description": (
                    "Riclassificazione: dopo quanti secondi dall'avvio un'esecuzione "
                    "ancora 'running' e' considerata bloccata."
                ),
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key = 'job_health.reclassification.stale_after_seconds'")

    op.execute("ALTER TABLE audit_log DROP CONSTRAINT ck_audit_log_event_type")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_event_type "
        "CHECK (event_type IN (" + ", ".join(f"'{e}'" for e in _OLD_EVENT_TYPES) + "))"
    )

    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        "CHECK (job_kind IN (" + ", ".join(f"'{k}'" for k in _OLD_JOB_KINDS) + "))"
    )

"""system_settings: configurazione di istanza, prima applicazione job_health

Revision ID: 0020_system_settings
Revises: 0019_ai_classification_decoupled
Create Date: 2026-08-13

Tabella globale (no RLS, come `banks`/`bank_parsers`): sono parametri
operativi dell'infrastruttura condivisa (worker/Redis), non una scelta di un
singolo tenant. Prima applicazione: soglie di staleness lette dal rilevatore
generico di job bloccati (`app/services/job_health.py`) — vedi le chiavi
`job_health.*` seedate qui sotto. Nessun endpoint di scrittura protetto da
ruolo admin per ora (quel ruolo non esiste ancora, vedi
`app/models/workspace_member.py`): rischio accettato esplicitamente in
attesa del futuro rework admin/utente.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020_system_settings"
down_revision: Union[str, None] = "0019_ai_classification_decoupled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Soglie iniziali coerenti con i timeout arq gia' configurati per ciascun job
# (vedi app/core/config.py): "stale" = nessuna attivita' rilevata da piu' di
# questi secondi mentre lo stato e' non-terminale — segno che il worker che
# lo eseguiva e' morto senza poter scrivere lo stato finale.
#   - import: timeout job 300s + margine 120s.
#   - ai_classification: NON basato sul suo timeout totale (1800s) ma
#     sull'heartbeat naturale del progresso per-transazione (gia' scritto ad
#     ogni riga classificata) + margine breve: rileva un crash in minuti,
#     non in mezz'ora.
#   - market_data_refresh/snapshot_rebuild/google_sheets_export: una soglia
#     PER JOB KIND (non una condivisa su tutta job_runs, vedi pagina
#     Impostazioni > Job): nessun heartbeat in-loop per questi, stesso
#     principio di "import" sul timeout globale di default (300s) + margine.
#
# `jobs.<kind>.enabled`: on/off dei 3 job SCHEDULATI (cron) — import/
# classificazione AI/export Google Sheets sono innescati da un'azione utente,
# non hanno un equivalente qui (il loro on/off vive altrove: profilo AI
# attivo per workspace, GOOGLE_ENABLED di istanza). Letto dal job stesso a
# ogni esecuzione: disattivarlo NON rimuove il cron (arq lo registra
# all'avvio del processo, non si puo' togliere a runtime), il job
# semplicemente non fa nulla quando scatta.
_SEED_SETTINGS = [
    {
        "key": "job_health.import.stale_after_seconds",
        "value": 420,
        "description": "Import: dopo quanti secondi senza aggiornamenti un job in 'processing'/'parsing' e' considerato bloccato (worker probabilmente terminato in modo anomalo).",
    },
    {
        "key": "job_health.ai_classification.stale_after_seconds",
        "value": 120,
        "description": "Classificazione AI: dopo quanti secondi senza avanzamento del contatore un job in 'pending'/'running' e' considerato bloccato.",
    },
    {
        "key": "job_health.market_data_refresh.stale_after_seconds",
        "value": 420,
        "description": "Refresh prezzi di mercato: dopo quanti secondi dall'avvio un'esecuzione ancora 'running' e' considerata bloccata.",
    },
    {
        "key": "job_health.snapshot_rebuild.stale_after_seconds",
        "value": 420,
        "description": "Ricalcolo snapshot patrimonio: dopo quanti secondi dall'avvio un'esecuzione ancora 'running' e' considerata bloccata.",
    },
    {
        "key": "job_health.google_sheets_export.stale_after_seconds",
        "value": 420,
        "description": "Export Google Sheets: dopo quanti secondi dall'avvio un'esecuzione ancora 'running' e' considerata bloccata.",
    },
    {
        "key": "jobs.market_data_refresh.enabled",
        "value": True,
        "description": "Refresh automatico giornaliero dei prezzi di mercato. Il trigger manuale resta sempre disponibile indipendentemente da questo valore.",
    },
    {
        "key": "jobs.snapshot_rebuild.enabled",
        "value": True,
        "description": "Ricalcolo automatico giornaliero dello snapshot di patrimonio. Il trigger manuale resta sempre disponibile indipendentemente da questo valore.",
    },
    {
        "key": "jobs.stale_job_reaper.enabled",
        "value": True,
        "description": "Rilevatore di job bloccati (questo stesso meccanismo). Disattivarlo significa che un job bloccato da un crash del worker non verra' piu' rilevato automaticamente.",
    },
]


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("default_value", postgresql.JSONB, nullable=False),
        sa.Column("description", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
    )

    system_settings_table = sa.table(
        "system_settings",
        sa.column("key", sa.String),
        sa.column("value", postgresql.JSONB),
        sa.column("default_value", postgresql.JSONB),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        system_settings_table,
        [
            {
                "key": setting["key"],
                "value": setting["value"],
                "default_value": setting["value"],
                "description": setting["description"],
            }
            for setting in _SEED_SETTINGS
        ],
    )


def downgrade() -> None:
    op.drop_table("system_settings")

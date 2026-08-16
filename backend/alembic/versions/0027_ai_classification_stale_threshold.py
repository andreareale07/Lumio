"""job_health.ai_classification.stale_after_seconds: 120 -> 600

Revision ID: 0027_ai_stale_threshold
Revises: 0026_transaction_needs_review
Create Date: 2026-08-16

Bug trovato in produzione (import reale dell'utente, provider Ollama
locale): la soglia seminata da 0020 (120s) era tarata su
`ai_classify_timeout_seconds` quando questo valeva ancora 30s (default
storico, pensato per provider cloud) — dava un margine di ~4 tentativi
falliti prima di scattare. Con `ai_classify_timeout_seconds` alzato a 120s
(inferenza locale, molto piu' lenta) le due soglie sono diventate UGUALI:
il rilevatore di job bloccati (`app/services/job_health.py`, gira ogni 2
minuti) marcava l'import 'failed' dopo un solo tentativo ancora in corso,
mentre il circuit breaker del job stesso (3 tentativi consecutivi, vedi
`_MAX_CONSECUTIVE_PROVIDER_ERRORS` in ai_classification_job.py) aveva
bisogno fino a 360s per arrivare alla sua propria conclusione — due
fallimenti indipendenti per la stessa causa, quello del rilevatore sempre
prima e piu' fuorviante (fa sembrare bloccato un job che stava ancora
legittimamente ritentando).

600s da margine sopra i 360s nel caso peggiore (3 tentativi x 120s) senza
essere eccessivo per un vero blocco del worker.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027_ai_stale_threshold"
down_revision: Union[str, None] = "0026_transaction_needs_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEY = "job_health.ai_classification.stale_after_seconds"


def upgrade() -> None:
    op.execute(
        f"UPDATE system_settings SET value = '600', default_value = '600' "
        f"WHERE key = '{_KEY}' AND value = '120'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE system_settings SET value = '120', default_value = '120' "
        f"WHERE key = '{_KEY}' AND value = '600'"
    )

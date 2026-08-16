"""imports: messaggio di errore persistito per il job di classificazione AI

Revision ID: 0023_ai_classification_error
Revises: 0022_category_taxonomy_reseed
Create Date: 2026-08-16

Gap UX reale scoperto testando dal vivo un'interruzione del provider AI
(container Ollama remoto spento a meta' import, per simulare un crash): il
job di classificazione transita correttamente a `ai_classification_status=
'failed'` (vedi worker/jobs/ai_classification_job.py, fix del contatore di
progresso che fingeva successo durante l'interruzione), ma l'utente non
aveva alcun modo di sapere PERCHE' — l'indicatore "x/N" nella UI
(AiClassificationProgress.tsx) semplicemente smette di essere mostrato non
appena lo stato non e' piu' 'pending'/'running', senza lasciare traccia del
motivo. Stesso ruolo di `imports.error_message` (gia' esistente per il
parsing del file), ma per questo job separato.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_ai_classification_error"
down_revision: Union[str, None] = "0022_category_taxonomy_reseed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("imports", sa.Column("ai_classification_error_message", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("imports", "ai_classification_error_message")

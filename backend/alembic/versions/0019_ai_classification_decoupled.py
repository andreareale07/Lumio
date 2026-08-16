"""imports: campi per la classificazione AI disaccoppiata dal job di import

Revision ID: 0019_ai_classification_decoupled
Revises: 0018_import_deleted_event
Create Date: 2026-08-13

Bug reale scoperto sui dati veri dell'utente: il timeout del job di import
(arq `job_timeout`, 300s) e' un budget CUMULATIVO su tutto il job, non per
singola chiamata AI — un import con molte righe non classificate dalle
regole poteva quindi essere cancellato a meta' solo per il tempo totale
speso a interrogare il provider AI in sequenza. La classificazione AI viene
quindi spostata in un job separato (vedi ai_classification_job.py), con un
proprio timeout piu' ampio e progresso tracciato qui per l'indicatore "x/N"
richiesto dall'utente in UI.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_ai_classification_decoupled"
down_revision: Union[str, None] = "0018_import_deleted_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AI_CLASSIFICATION_STATUSES = ("pending", "running", "completed", "failed", "skipped")


def upgrade() -> None:
    op.add_column("imports", sa.Column("ai_classification_status", sa.String(), nullable=True))
    op.add_column(
        "imports",
        sa.Column("ai_transactions_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "imports",
        sa.Column("ai_transactions_classified", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "ck_imports_ai_classification_status",
        "imports",
        "ai_classification_status IN ("
        + ", ".join(f"'{s}'" for s in AI_CLASSIFICATION_STATUSES)
        + ") OR ai_classification_status IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_imports_ai_classification_status", "imports", type_="check")
    op.drop_column("imports", "ai_transactions_classified")
    op.drop_column("imports", "ai_transactions_total")
    op.drop_column("imports", "ai_classification_status")

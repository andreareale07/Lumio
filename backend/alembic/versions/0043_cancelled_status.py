"""stato 'cancelled' per classificazione AI degli import e per i job_runs

Revision ID: 0043_cancelled_status
Revises: 0042_ai_run_events
Create Date: 2026-10-24

L'utente puo' interrompere una classificazione AI in corso (per un import o
la riclassificazione del workspace). Uno stato dedicato distingue "fermata da
me" da "fallita": le righe gia' classificate restano, e lo stato finale non
finisce tra gli errori. Allarga i due CHECK che elencano gli stati:
`ck_imports_ai_classification_status` e `ck_job_runs_status`.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0043_cancelled_status"
down_revision: Union[str, None] = "0042_ai_run_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_AI = ("pending", "running", "completed", "failed", "skipped")
_NEW_AI = _OLD_AI + ("cancelled",)
_OLD_JOB = ("running", "success", "failed")
_NEW_JOB = _OLD_JOB + ("cancelled",)


def _without_row_security(table: str, statement: str) -> None:
    """`imports` e `job_runs` hanno la RLS FORZATA: senza un'identita' di
    workspace un UPDATE dell'utente della migration non vede nessuna riga. Il
    proprietario della tabella sospende la RLS forzata solo per il tempo della
    pulizia e la ripristina subito, nella stessa transazione."""
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(statement)
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute("ALTER TABLE imports DROP CONSTRAINT ck_imports_ai_classification_status")
    op.execute(
        "ALTER TABLE imports ADD CONSTRAINT ck_imports_ai_classification_status "
        f"CHECK (ai_classification_status IN ({_in(_NEW_AI)}) OR ai_classification_status IS NULL)"
    )
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_status")
    op.execute(f"ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_status CHECK (status IN ({_in(_NEW_JOB)}))")


def downgrade() -> None:
    # Le righe 'cancelled' violerebbero il CHECK piu' stretto: si riportano a
    # lo stato "concluso" piu' vicino prima di ripristinarlo.
    _without_row_security("imports", "UPDATE imports SET ai_classification_status = 'completed' WHERE ai_classification_status = 'cancelled'")
    _without_row_security("job_runs", "UPDATE job_runs SET status = 'failed' WHERE status = 'cancelled'")
    op.execute("ALTER TABLE imports DROP CONSTRAINT ck_imports_ai_classification_status")
    op.execute(
        "ALTER TABLE imports ADD CONSTRAINT ck_imports_ai_classification_status "
        f"CHECK (ai_classification_status IN ({_in(_OLD_AI)}) OR ai_classification_status IS NULL)"
    )
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_status")
    op.execute(f"ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_status CHECK (status IN ({_in(_OLD_JOB)}))")

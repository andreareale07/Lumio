"""Detection overrides (ricorrenze/anomalie)

Revision ID: 0035_detection_overrides
Revises: 0034_account_classify_lang
Create Date: 2026-08-25

Piano `synchronous-chasing-pike.md`, FETTA 2 §2.8. Sola `create_table` + 3
indici + RLS — nessuna tabella derivata per le serie ricorrenti/anomalie
stesse (calcolate on-the-fly, §2.6): questa tabella persiste SOLO le
correzioni manuali dell'utente ("ignora questo segnale"), applicazione
diretta di CLAUDE.md ("le correzioni manuali hanno sempre priorita'
sull'AI").

Nessun tocco a `ck_job_runs_job_kind` (nessun job asincrono: il calcolo gira
in-request, vedi docstring di `app/services/detection.py`) ne' a
`ck_audit_log_event_type` (ignorare un suggerimento non e' un evento
finanziario auditabile come una decisione di dedup, migration 0033).

Due indici UNIQUE PARZIALI (uno per `override_type`), non un unique a 4
colonne: Postgres tratta i NULL come distinti, un unique su colonne
nullable non farebbe da vincolo per le righe con l'altro tipo.

RLS: stesso pattern standard del repo (ENABLE + FORCE, `is_workspace_member`
riusata cosi' com'e' per le 4 policy per comando — copiato da
`0033_transaction_dedup.py`).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0035_detection_overrides"
down_revision: Union[str, None] = "0034_account_classify_lang"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "detection_overrides",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("override_type", sa.String, nullable=False),
        sa.Column("series_key", sa.String(32), nullable=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String, nullable=False),
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "override_type IN ('recurring_series', 'anomaly')", name="ck_detection_overrides_type"
        ),
        sa.CheckConstraint("decision IN ('ignored', 'confirmed')", name="ck_detection_overrides_decision"),
        sa.CheckConstraint(
            "(override_type = 'recurring_series' AND series_key IS NOT NULL AND transaction_id IS NULL) "
            "OR (override_type = 'anomaly' AND transaction_id IS NOT NULL AND series_key IS NULL)",
            name="ck_detection_overrides_target",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="CASCADE",
            name="fk_detection_overrides_workspace_transaction",
        ),
    )
    op.create_index("ix_detection_overrides_workspace_id", "detection_overrides", ["workspace_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_detection_overrides_recurring_series "
        "ON detection_overrides (workspace_id, series_key) "
        "WHERE override_type = 'recurring_series'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_detection_overrides_anomaly "
        "ON detection_overrides (workspace_id, transaction_id) "
        "WHERE override_type = 'anomaly'"
    )

    op.execute("ALTER TABLE detection_overrides ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE detection_overrides FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY detection_overrides_select ON detection_overrides FOR SELECT
        USING (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY detection_overrides_insert ON detection_overrides FOR INSERT
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY detection_overrides_update ON detection_overrides FOR UPDATE
        USING (is_workspace_member(workspace_id))
        WITH CHECK (is_workspace_member(workspace_id));
        """
    )
    op.execute(
        """
        CREATE POLICY detection_overrides_delete ON detection_overrides FOR DELETE
        USING (is_workspace_member(workspace_id));
        """
    )


def downgrade() -> None:
    for policy in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS detection_overrides_{policy} ON detection_overrides")
    op.drop_table("detection_overrides")

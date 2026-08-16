"""audit_log: aggiunge IMPORT_DELETED all'elenco chiuso di event_type

Revision ID: 0018_import_deleted_event
Revises: 0017_audit_log
Create Date: 2026-08-13

Rework "elimina import": nuovo evento di audit log per l'eliminazione di un
import (SPEC §59) — l'elenco di event_type e' un CHECK constraint chiuso
(vedi 0017_audit_log.py), quindi un evento nuovo richiede sempre di
allargarlo qui, non solo in app/models/audit_log.py.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_import_deleted_event"
down_revision: Union[str, None] = "0017_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("IMPORT_DELETED",)


def upgrade() -> None:
    op.drop_constraint("ck_audit_log_event_type", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_event_type",
        "audit_log",
        "event_type IN (" + ", ".join(f"'{e}'" for e in _NEW_EVENT_TYPES) + ")",
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_log_event_type", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_event_type",
        "audit_log",
        "event_type IN (" + ", ".join(f"'{e}'" for e in _OLD_EVENT_TYPES) + ")",
    )

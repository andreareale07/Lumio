"""bank_parsers, imports.file_type/bank_id/bank_parser_id

Revision ID: 0005_bank_parsers
Revises: 0004_imports
Create Date: 2026-08-10

Milestone 05 — Trade Republic Parser.

`bank_parsers' e' un'entita' globale come `banks` (nessuna RLS, seedata da
questa migration): SPEC §17 la vuole separata dalla banca stessa perche' "i
formati PDF possono cambiare" — una banca puo' avere piu' righe (versioni),
il codice concreto vive nel registro Python (`app/parsers/__init__.py`), qui
si traccia solo quale banca/versione un import ha effettivamente usato.

`imports.file_type` distingue i due canali (CSV, esistente da M04; PDF, nuovo
qui) con un default 'csv' cosi' le righe gia' esistenti restano valide senza
backfill esplicito. `bank_id`/`bank_parser_id` sono nullable perche' hanno
senso solo per file_type='pdf' (per CSV la banca non viene rilevata, l'utente
sceglie/mappa le colonne a mano) — nessun CHECK incrociato tra file_type e
questi due campi: sarebbe verificabile solo in applicazione, dove infatti il
codice li valorizza insieme o li lascia entrambi NULL.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.seed_data import BANK_PARSERS

# revision identifiers, used by Alembic.
revision: str = "0005_bank_parsers"
down_revision: Union[str, None] = "0004_imports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- bank_parsers (globale, no RLS) -------------------------------------

    op.create_table(
        "bank_parsers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("banks.id"), nullable=False),
        sa.Column("parser_type", sa.String, nullable=False),
        sa.Column("version", sa.String, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("bank_id", "parser_type", "version", name="uq_bank_parsers_bank_type_version"),
    )

    bank_parsers_table = sa.table(
        "bank_parsers",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("bank_id", postgresql.UUID(as_uuid=True)),
        sa.column("parser_type", sa.String),
        sa.column("version", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        bank_parsers_table,
        [
            {
                "id": uuid.UUID(bp["id"]),
                "bank_id": uuid.UUID(bp["bank_id"]),
                "parser_type": bp["parser_type"],
                "version": bp["version"],
                "is_active": bp["is_active"],
            }
            for bp in BANK_PARSERS
        ],
    )

    # --- imports: nuovo canale PDF ------------------------------------------

    op.add_column(
        "imports",
        sa.Column("file_type", sa.String, nullable=False, server_default=sa.text("'csv'")),
    )
    op.add_column(
        "imports",
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("banks.id"), nullable=True),
    )
    op.add_column(
        "imports",
        sa.Column(
            "bank_parser_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bank_parsers.id"), nullable=True
        ),
    )
    op.create_check_constraint("ck_imports_file_type", "imports", "file_type IN ('csv', 'pdf')")


def downgrade() -> None:
    op.drop_constraint("ck_imports_file_type", "imports", type_="check")
    op.drop_column("imports", "bank_parser_id")
    op.drop_column("imports", "bank_id")
    op.drop_column("imports", "file_type")

    op.drop_table("bank_parsers")

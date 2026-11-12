"""regole con piu' condizioni (E/O) e condizione sull'importo

Revision ID: 0048_rule_conditions
Revises: 0047_open_banking_hardening
Create Date: 2026-11-12

- `rules.conditions` (JSONB, 1..10 elementi) sostituisce le colonne
  `field`/`operator`/`value`: ogni regola esistente diventa una lista con la
  sua unica condizione. `rules.match_mode` ('all' = E, 'any' = O).
- Il backfill gira con NO FORCE ROW LEVEL SECURITY nella stessa transazione:
  sotto FORCE un UPDATE senza identita' RLS vedrebbe zero righe senza errore
  (stessa tecnica di 0041/0043).
- Downgrade con perdita dichiarata: conserva solo la prima condizione di
  testo di ogni regola; una regola senza condizioni di testo (solo importo)
  torna disattivata con valore segnaposto.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048_rule_conditions"
down_revision: Union[str, None] = "0047_open_banking_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rules", sa.Column("conditions", postgresql.JSONB, nullable=True))
    op.add_column("rules", sa.Column("match_mode", sa.String, nullable=False, server_default=sa.text("'all'")))

    op.execute("ALTER TABLE rules NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE rules SET conditions = jsonb_build_array("
        "jsonb_build_object('field', field, 'operator', operator, 'value', value))"
    )
    op.execute("ALTER TABLE rules FORCE ROW LEVEL SECURITY")

    op.alter_column("rules", "conditions", nullable=False)
    op.create_check_constraint("ck_rules_match_mode", "rules", "match_mode IN ('all', 'any')")
    op.create_check_constraint(
        "ck_rules_conditions",
        "rules",
        "jsonb_typeof(conditions) = 'array' AND jsonb_array_length(conditions) BETWEEN 1 AND 10",
    )

    op.drop_constraint("ck_rules_field", "rules", type_="check")
    op.drop_constraint("ck_rules_operator", "rules", type_="check")
    op.drop_column("rules", "field")
    op.drop_column("rules", "operator")
    op.drop_column("rules", "value")


def downgrade() -> None:
    op.add_column("rules", sa.Column("field", sa.String, nullable=True))
    op.add_column("rules", sa.Column("operator", sa.String, nullable=True))
    op.add_column("rules", sa.Column("value", sa.String, nullable=True))

    op.execute("ALTER TABLE rules NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE rules r SET
          field = t.field, operator = t.operator, value = t.value
        FROM (
          SELECT r2.id,
                 first_text ->> 'field' AS field,
                 first_text ->> 'operator' AS operator,
                 first_text ->> 'value' AS value
          FROM rules r2
          LEFT JOIN LATERAL (
            SELECT c AS first_text
            FROM jsonb_array_elements(r2.conditions) WITH ORDINALITY AS e(c, ord)
            WHERE c ->> 'field' IN ('description', 'merchant')
            ORDER BY ord
            LIMIT 1
          ) f ON TRUE
        ) t
        WHERE r.id = t.id
        """
    )
    op.execute(
        "UPDATE rules SET field = 'description', operator = 'contains', value = '(solo importo)', "
        "is_active = false WHERE field IS NULL"
    )
    op.execute("ALTER TABLE rules FORCE ROW LEVEL SECURITY")

    op.alter_column("rules", "field", nullable=False)
    op.alter_column("rules", "operator", nullable=False)
    op.alter_column("rules", "value", nullable=False)
    op.create_check_constraint("ck_rules_field", "rules", "field IN ('description', 'merchant')")
    op.create_check_constraint(
        "ck_rules_operator",
        "rules",
        "operator IN ('equals', 'contains', 'starts_with', 'ends_with', 'regex', 'merchant_equals')",
    )

    op.drop_constraint("ck_rules_conditions", "rules", type_="check")
    op.drop_constraint("ck_rules_match_mode", "rules", type_="check")
    op.drop_column("rules", "conditions")
    op.drop_column("rules", "match_mode")

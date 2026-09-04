"""Fiscalita' conti titoli — FETTA 1 (docs/SPEC_TAX_REGIME.md)

Revision ID: 0039_tax_domain
Revises: 0038_import_account_after_upload
Create Date: 2026-09-04

Quattro tabelle per rispondere in modo deterministico e auditabile a "quanto
zainetto fiscale ho, formato quando, che scade quando, e perche' quel numero
e' quel numero" — per regime amministrato (per intermediario) e dichiarativo
(aggregato personale). Il regolamento fiscale stesso (aliquote, matrice di
compensabilita', coefficienti) vive come dato puro in `app/tax/`, MAI in
queste tabelle: solo gli input utente non ricostruibili sono persistiti.

- `workspace_tax_residences`: residenza fiscale per anno solare (l'Italia
  non ha split-year — l'anno E' l'intervallo, niente `valid_from`/`valid_to`).
- `financial_account_tax_regimes`: periodi di regime per conto, APPEND-ONLY
  (stesso pattern minimo di `financial_account_iban_history`, 0009), nessun
  `valid_to` — l'intervallo di una riga e' `[effective_from, next.effective_from)`,
  risolto a lettura ordinando per `effective_from`. `regime_code` senza CHECK
  enum: vocabolario della giurisdizione (`app/tax/registry.py`), validato al
  confine applicativo.
- `asset_tax_classifications`: override utente della classe fiscale
  derivata — riga presente solo se l'utente sovrascrive il default.
- `tax_loss_opening_balances`: saldi di apertura dello zainetto, unica fonte
  che alimenta il calcolo in FETTA 1 (il motore a lotti e' FETTA 2).
  `financial_account_id` NULL = perimetro dichiarativo aggregato,
  valorizzato = perimetro amministrato per quell'intermediario — due indici
  UNIQUE parziali per l'unicita' (NULL non e' mai uguale a NULL, un
  UniqueConstraint singolo non basterebbe sul perimetro aggregato).

RLS: stesso pattern di tutte le tabelle precedenti (ENABLE + FORCE,
`is_workspace_member` per le 4 policy separate per comando — mai `FOR ALL`,
vedi 0033). FK composite `(workspace_id, fk_id)` verso `(parent.workspace_id,
parent.id)`: `financial_accounts`/`assets` hanno gia' l'UniqueConstraint
richiesto (0004/0026), nessuna ALTER sui genitori.

Estende `ck_audit_log_event_type` con "TAX_SETTING_CHANGED" (stesso pattern
di 0018/0025/0033): un cambio di residenza/regime/classificazione/apertura
e' auditabile.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0039_tax_domain"
down_revision: Union[str, None] = "0038_import_account_after_upload"
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
    "IMPORT_DELETED",
    "RECLASSIFICATION_RUN",
    "TRANSACTION_DEDUP_DECISION",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("TAX_SETTING_CHANGED",)

_NEW_TABLES = (
    "workspace_tax_residences",
    "financial_account_tax_regimes",
    "asset_tax_classifications",
    "tax_loss_opening_balances",
)


def upgrade() -> None:
    # --- workspace_tax_residences --------------------------------------------

    op.create_table(
        "workspace_tax_residences",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("jurisdiction_code", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "fiscal_year", name="uq_workspace_tax_residences_year"),
    )
    op.create_index("ix_workspace_tax_residences_workspace_id", "workspace_tax_residences", ["workspace_id"])

    # --- financial_account_tax_regimes ---------------------------------------

    op.create_table(
        "financial_account_tax_regimes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("regime_code", sa.String, nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_financial_account_tax_regimes_workspace_account",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "financial_account_id",
            "effective_from",
            name="uq_financial_account_tax_regimes_effective_from",
        ),
    )
    op.create_index(
        "ix_financial_account_tax_regimes_workspace_id", "financial_account_tax_regimes", ["workspace_id"]
    )
    op.create_index(
        "ix_financial_account_tax_regimes_financial_account_id",
        "financial_account_tax_regimes",
        ["financial_account_id"],
    )

    # --- asset_tax_classifications --------------------------------------------

    op.create_table(
        "asset_tax_classifications",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction_code", sa.String, nullable=False),
        sa.Column("asset_class", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["workspace_id", "asset_id"],
            ["assets.workspace_id", "assets.id"],
            ondelete="CASCADE",
            name="fk_asset_tax_classifications_workspace_asset",
        ),
        sa.UniqueConstraint(
            "workspace_id", "asset_id", "jurisdiction_code", name="uq_asset_tax_classifications_asset_jurisdiction"
        ),
    )
    op.create_index("ix_asset_tax_classifications_workspace_id", "asset_tax_classifications", ["workspace_id"])
    op.create_index("ix_asset_tax_classifications_asset_id", "asset_tax_classifications", ["asset_id"])

    # --- tax_loss_opening_balances --------------------------------------------

    op.create_table(
        "tax_loss_opening_balances",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("formation_date", sa.Date, nullable=False),
        sa.Column("formed_under_ruleset_code", sa.String, nullable=False),
        sa.Column("income_category", sa.String, nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_tax_loss_opening_balances_workspace_account",
        ),
    )
    op.create_index("ix_tax_loss_opening_balances_workspace_id", "tax_loss_opening_balances", ["workspace_id"])
    op.create_index(
        "ix_tax_loss_opening_balances_financial_account_id",
        "tax_loss_opening_balances",
        ["financial_account_id"],
    )
    # Due indici UNIQUE parziali (mai un UniqueConstraint singolo: NULL non
    # e' mai uguale a NULL, non basterebbe a impedire duplicati nel
    # perimetro dichiarativo aggregato) — si escludono a vicenda per
    # costruzione, nessuna sovrapposizione possibile.
    op.create_index(
        "uq_tax_loss_opening_balances_per_account",
        "tax_loss_opening_balances",
        ["workspace_id", "financial_account_id", "formation_date"],
        unique=True,
        postgresql_where=sa.text("financial_account_id IS NOT NULL"),
    )
    op.create_index(
        "uq_tax_loss_opening_balances_aggregate",
        "tax_loss_opening_balances",
        ["workspace_id", "formation_date"],
        unique=True,
        postgresql_where=sa.text("financial_account_id IS NULL"),
    )

    # --- RLS -------------------------------------------------------------------

    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_select ON {table} FOR SELECT
            USING (is_workspace_member(workspace_id));
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_insert ON {table} FOR INSERT
            WITH CHECK (is_workspace_member(workspace_id));
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_update ON {table} FOR UPDATE
            USING (is_workspace_member(workspace_id))
            WITH CHECK (is_workspace_member(workspace_id));
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_delete ON {table} FOR DELETE
            USING (is_workspace_member(workspace_id));
            """
        )

    # --- audit_log: nuovo evento -----------------------------------------------

    op.execute("ALTER TABLE audit_log DROP CONSTRAINT ck_audit_log_event_type")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_event_type "
        "CHECK (event_type IN (" + ", ".join(f"'{e}'" for e in _NEW_EVENT_TYPES) + "))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT ck_audit_log_event_type")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_event_type "
        "CHECK (event_type IN (" + ", ".join(f"'{e}'" for e in _OLD_EVENT_TYPES) + "))"
    )

    for table in reversed(_NEW_TABLES):
        for policy in ("select", "insert", "update", "delete"):
            op.execute(f"DROP POLICY IF EXISTS {table}_{policy} ON {table}")

    for table in reversed(_NEW_TABLES):
        op.drop_table(table)

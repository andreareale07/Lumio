"""open banking: credenziali per utente, connessioni, conti, transactions.external_id

Revision ID: 0044_open_banking
Revises: 0043_cancelled_status
Create Date: 2026-11-06

Connettore Open Banking (Enable Banking). Tre tabelle con RLS FORCE e 4 policy
separate, tutte OWNER-ONLY (`owner_user_id` = identita' corrente + membro del
workspace): i Terms del provider vietano di rendere accessibili le credenziali
a terzi, quindi nemmeno gli altri membri del workspace vedono credenziali,
sessioni o conti di un utente.

Inoltre: `transactions.external_id` (id della banca, indice parziale NON unique),
`imports.file_type` esteso a 'open_banking' (ogni sync crea un Import, cosi' la
pipeline di dedup/review resta unica) e `ck_audit_log_event_type` con
BANK_CONNECTED/BANK_DISCONNECTED. Lo stato della sync vive su `bank_connections`
(per connessione), non in `job_runs`: nessun nuovo job_kind.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_open_banking"
down_revision: Union[str, None] = "0043_cancelled_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OWNER = (
    "owner_user_id = current_setting('app.current_user_id', true)::uuid "
    "AND is_workspace_member(workspace_id)"
)


def _owner_policies(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({_OWNER})")
    op.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({_OWNER})")
    op.execute(f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({_OWNER}) WITH CHECK ({_OWNER})")
    op.execute(f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({_OWNER})")


def _drop_policies(table: str) -> None:
    for policy in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS {table}_{policy} ON {table}")


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
    "TAX_SETTING_CHANGED",
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("BANK_CONNECTED", "BANK_DISCONNECTED")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    uuid_pk = sa.Column(
        "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    op.create_table(
        "open_banking_credentials",
        uuid_pk,
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("application_id", sa.String, nullable=True),
        sa.Column("private_key_encrypted", sa.String, nullable=False),
        sa.Column("certificate_pem", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("provider IN ('enable_banking')", name="ck_open_banking_credentials_provider"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_user_id", "provider", name="uq_open_banking_credentials_owner_provider"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_open_banking_credentials_workspace_id"),
    )
    op.create_index("ix_open_banking_credentials_workspace_id", "open_banking_credentials", ["workspace_id"])
    _owner_policies("open_banking_credentials")

    op.create_table(
        "bank_connections",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("aspsp_name", sa.String, nullable=False),
        sa.Column("aspsp_country", sa.String(2), nullable=False),
        sa.Column("psu_type", sa.String, nullable=False, server_default=sa.text("'personal'")),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("state_nonce_hash", sa.String(64), nullable=True),
        sa.Column("authorization_id", sa.String, nullable=True),
        sa.Column("session_id_encrypted", sa.String, nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'revoked', 'error')", name="ck_bank_connections_status"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["open_banking_credentials.workspace_id", "open_banking_credentials.id"],
            ondelete="CASCADE",
            name="fk_bank_connections_workspace_credential",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_bank_connections_workspace_id"),
    )
    op.create_index("ix_bank_connections_workspace_id", "bank_connections", ["workspace_id"])
    _owner_policies("bank_connections")

    op.create_table(
        "bank_connection_accounts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_account_uid", sa.String, nullable=False),
        sa.Column("iban", sa.String, nullable=True),
        sa.Column("name", sa.String, nullable=True),
        sa.Column("product", sa.String, nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("cash_account_type", sa.String, nullable=True),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_booked_date", sa.Date, nullable=True),
        sa.Column("transactions_imported", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["bank_connections.workspace_id", "bank_connections.id"],
            ondelete="CASCADE",
            name="fk_bank_connection_accounts_workspace_connection",
        ),
        sa.UniqueConstraint("connection_id", "provider_account_uid", name="uq_bank_connection_accounts_uid"),
    )
    # SET NULL solo su financial_account_id: con la FK composita standard
    # Postgres azzererebbe anche workspace_id (NOT NULL). L'elenco colonne di
    # ON DELETE SET NULL e' supportato da PostgreSQL 15+ (il progetto usa 16).
    op.execute(
        "ALTER TABLE bank_connection_accounts ADD CONSTRAINT fk_bank_connection_accounts_workspace_account "
        "FOREIGN KEY (workspace_id, financial_account_id) "
        "REFERENCES financial_accounts (workspace_id, id) ON DELETE SET NULL (financial_account_id)"
    )
    op.create_index("ix_bank_connection_accounts_workspace_id", "bank_connection_accounts", ["workspace_id"])
    op.create_index("ix_bank_connection_accounts_connection_id", "bank_connection_accounts", ["connection_id"])
    _owner_policies("bank_connection_accounts")

    # --- transactions.external_id -------------------------------------------
    op.add_column("transactions", sa.Column("external_id", sa.String, nullable=True))
    op.execute(
        "CREATE INDEX ix_transactions_workspace_account_external_id "
        "ON transactions (workspace_id, financial_account_id, external_id) WHERE external_id IS NOT NULL"
    )

    # --- imports.file_type: aggiungere 'open_banking' -------------------------
    op.execute("ALTER TABLE imports DROP CONSTRAINT ck_imports_file_type")
    op.execute(
        "ALTER TABLE imports ADD CONSTRAINT ck_imports_file_type "
        f"CHECK (file_type IN ({_in(('csv', 'pdf', 'open_banking'))}))"
    )

    # --- list_active_bank_connections() (SECURITY DEFINER, per il cron) -------
    # Il cron non ha un'identita' RLS e le tabelle sono owner-only: stessa
    # soluzione di `list_workspace_owners()` (0010). BYPASSRLS non da'
    # privilegi sulle tabelle, serve il GRANT esplicito (vedi memoria RLS).
    # Privilegio di COLONNA, non di tabella: il ruolo helper non deve poter
    # leggere `session_id_encrypted` ne' le altre colonne sensibili.
    op.execute("GRANT SELECT (id, workspace_id, owner_user_id, status) ON bank_connections TO lumio_rls_helper")
    op.execute(
        """
        CREATE FUNCTION list_active_bank_connections()
        RETURNS TABLE(connection_id uuid, workspace_id uuid, owner_user_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT id, workspace_id, owner_user_id FROM public.bank_connections WHERE status = 'active';
        $$;
        """
    )
    op.execute("ALTER FUNCTION list_active_bank_connections() OWNER TO lumio_rls_helper")
    # Una SECURITY DEFINER va chiusa a PUBLIC. Il ruolo applicativo e' membro di
    # `lumio_rls_helper` (INHERIT) e ne eredita l'EXECUTE: nessun nome di ruolo
    # applicativo hardcoded, valido anche con Postgres esterno.
    op.execute("REVOKE ALL ON FUNCTION list_active_bank_connections() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION list_active_bank_connections() TO lumio_rls_helper")

    # --- audit_log.event_type: BANK_CONNECTED / BANK_DISCONNECTED -------------
    _replace_audit_check(_NEW_EVENT_TYPES)


def _replace_audit_check(events: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT ck_audit_log_event_type")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT ck_audit_log_event_type "
        f"CHECK (event_type IN ({_in(events)}))"
    )


def _without_row_security(table: str, statement: str) -> None:
    """Tabelle con RLS FORZATA: senza identita' un UPDATE/DELETE della migration
    non vede righe. Sospesa solo per la pulizia, ripristinata nella stessa
    transazione (stesso schema di 0043)."""
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(statement)
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    _without_row_security(
        "audit_log", "DELETE FROM audit_log WHERE event_type IN ('BANK_CONNECTED', 'BANK_DISCONNECTED')"
    )
    _replace_audit_check(_OLD_EVENT_TYPES)

    # Le righe 'open_banking' violerebbero il CHECK piu' stretto: si riportano
    # a 'csv' (le transazioni collegate restano, RESTRICT sulla FK).
    _without_row_security("imports", "UPDATE imports SET file_type = 'csv' WHERE file_type = 'open_banking'")
    op.execute("ALTER TABLE imports DROP CONSTRAINT ck_imports_file_type")
    op.execute(
        "ALTER TABLE imports ADD CONSTRAINT ck_imports_file_type "
        f"CHECK (file_type IN ({_in(('csv', 'pdf'))}))"
    )

    op.execute("DROP INDEX IF EXISTS ix_transactions_workspace_account_external_id")
    op.drop_column("transactions", "external_id")

    op.execute("DROP FUNCTION IF EXISTS list_active_bank_connections()")
    op.execute("REVOKE SELECT ON bank_connections FROM lumio_rls_helper")
    for table in ("bank_connection_accounts", "bank_connections", "open_banking_credentials"):
        _drop_policies(table)
        op.drop_table(table)

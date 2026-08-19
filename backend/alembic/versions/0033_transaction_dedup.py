"""Transaction Deduplication Engine

Revision ID: 0033_transaction_dedup
Revises: 0032_asset_prices_updated_at
Create Date: 2026-08-19

docs/SPEC_DEDUP_TRANSACTION.md. Introduce un secondo livello di dedup, a
livello di SINGOLA transazione (l'unico esistente finora, `imports.
file_hash`, opera sull'intero file — vedi migration 0004 — e non rileva
estratti conto sovrapposti con contenuto diverso ma movimenti in comune).

- `transactions.dedup_fingerprint`: SHA-256 deterministico dei campi di
  identita' (workspace+account+data+importo+currency+descrizione
  normalizzata+tipo), calcolato da
  `app.services.transaction_dedup.compute_dedup_fingerprint`. NON UNIQUE
  (SPEC §3): due transazioni legittimamente identiche devono poter
  coesistere, il matching e' per occorrenze (SPEC §11), non per esistenza
  del fingerprint. Backfill in batch (nessun precedente in questo progetto
  per un valore calcolato da altre colonne della stessa riga — a differenza
  di `needs_review`/`kind`/ecc., sempre una costante): cursore per `id`,
  2000 righe per iterazione, mai un caricamento completo in memoria.
  `description_normalized IS NULL` (transazioni create manualmente prima di
  questo cambiamento, vedi app/api/v1/transactions.py) ricade sul fallback
  legacy della funzione, che emette un warning applicativo — atteso qui, non
  altrove.
- `transaction_dedup_decisions`: relazione persistente utente-decisa tra un
  candidato ambiguo e una transazione esistente specifica (SPEC §17), mai
  una modifica del fingerprint.
- `transaction_review_items`: righe di un import per cui l'engine ha
  trovato un candidato ambiguo (stesso core key, descrizione diversa) —
  snapshot completo della riga parsata, nessuna Transaction creata finche'
  l'utente non decide (SPEC §15/§16).
- `imports.transactions_duplicate` / `transactions_review_pending`: nuovi
  contatori per il report di fine import (SPEC §19); `transactions_imported`
  cambia significato (solo le righe realmente persistite, non piu'
  incondizionatamente `len(rows)` — vedi app/worker/jobs/import_job.py).

RLS: stesso pattern di tutte le tabelle precedenti (ENABLE + FORCE,
`is_workspace_member` riusata cosi' com'e' per le 4 policy per comando).

Estende anche `ck_audit_log_event_type` con "TRANSACTION_DEDUP_DECISION"
(stesso pattern di 0018/0025: un evento nuovo richiede di allargare il CHECK
constraint, non solo `app/models/audit_log.py`) — ogni decisione IMPORTA
COMUNQUE/NON IMPORTARE su una voce di REVIEW e' auditabile (SPEC §33).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.transaction_dedup import compute_dedup_fingerprint

# revision identifiers, used by Alembic.
revision: str = "0033_transaction_dedup"
down_revision: Union[str, None] = "0032_asset_prices_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BATCH_SIZE = 2000

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
)
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES + ("TRANSACTION_DEDUP_DECISION",)

_transactions_table = sa.table(
    "transactions",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("workspace_id", postgresql.UUID(as_uuid=True)),
    sa.column("financial_account_id", postgresql.UUID(as_uuid=True)),
    sa.column("transaction_date", sa.Date),
    sa.column("amount", sa.Numeric(18, 2)),
    sa.column("currency", sa.String),
    sa.column("description_normalized", sa.String),
    sa.column("description_raw", sa.String),
    sa.column("transaction_type", sa.String),
    sa.column("dedup_fingerprint", sa.String),
)


def _backfill_dedup_fingerprints(conn: sa.engine.Connection) -> None:
    # `transactions` ha RLS FORCE: la connessione della migration gira come
    # lumio_app SENZA `app.current_user_id` impostato (nessuna identita'
    # utente in un contesto di migration), quindi senza bypass la SELECT
    # sotto vedrebbe zero righe per ogni workspace — non un errore, un filtro
    # RLS silenzioso — lasciando `dedup_fingerprint` NULL su tutte le righe
    # esistenti e facendo fallire la successiva `ALTER COLUMN SET NOT NULL`
    # (quella e' un'operazione DDL, ignora la RLS, quindi vede correttamente
    # le righe rimaste NULL). `lumio_rls_helper` e' lo stesso ruolo BYPASSRLS
    # gia' usato per il reseed di categorie/valute nei test (conftest.py) e
    # dalle funzioni SECURITY DEFINER della RLS stessa. BYPASSRLS non basta
    # da solo: serve anche il GRANT sulla colonna (principio di minimo
    # privilegio — stesso pattern di 0003/0006/0014/0029, che concedono
    # esplicitamente a lumio_rls_helper solo cio' che serve, mai un GRANT
    # generico), altrimenti l'UPDATE fallisce con "permission denied"
    # nonostante BYPASSRLS.
    conn.execute(sa.text("GRANT UPDATE (dedup_fingerprint) ON transactions TO lumio_rls_helper"))
    conn.execute(sa.text("SET ROLE lumio_rls_helper"))
    try:
        _run_backfill_batches(conn)
    finally:
        conn.execute(sa.text("RESET ROLE"))


def _run_backfill_batches(conn: sa.engine.Connection) -> None:
    last_id = None
    while True:
        query = sa.select(
            _transactions_table.c.id,
            _transactions_table.c.workspace_id,
            _transactions_table.c.financial_account_id,
            _transactions_table.c.transaction_date,
            _transactions_table.c.amount,
            _transactions_table.c.currency,
            _transactions_table.c.description_normalized,
            _transactions_table.c.description_raw,
            _transactions_table.c.transaction_type,
        ).order_by(_transactions_table.c.id).limit(_BATCH_SIZE)
        if last_id is not None:
            query = query.where(_transactions_table.c.id > last_id)
        rows = conn.execute(query).fetchall()
        if not rows:
            break
        for row in rows:
            fingerprint = compute_dedup_fingerprint(
                workspace_id=row.workspace_id,
                financial_account_id=row.financial_account_id,
                transaction_date=row.transaction_date,
                amount=row.amount,
                currency=row.currency,
                description_normalized=row.description_normalized,
                description_raw=row.description_raw,
                transaction_type=row.transaction_type,
            )
            conn.execute(
                sa.update(_transactions_table)
                .where(_transactions_table.c.id == row.id)
                .values(dedup_fingerprint=fingerprint)
            )
        last_id = rows[-1].id


def upgrade() -> None:
    # --- transactions.dedup_fingerprint -------------------------------------

    op.add_column("transactions", sa.Column("dedup_fingerprint", sa.String(64), nullable=True))
    _backfill_dedup_fingerprints(op.get_bind())
    op.alter_column("transactions", "dedup_fingerprint", nullable=False)

    op.create_index(
        "ix_transactions_workspace_account_fingerprint",
        "transactions",
        ["workspace_id", "financial_account_id", "dedup_fingerprint"],
    )
    op.create_index(
        "ix_transactions_dedup_core_key",
        "transactions",
        ["workspace_id", "financial_account_id", "transaction_date", "amount", "currency", "transaction_type"],
    )

    # --- transaction_dedup_decisions ----------------------------------------

    op.create_table(
        "transaction_dedup_decisions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("existing_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("new_fingerprint", sa.String(64), nullable=False),
        sa.Column("decision", sa.String, nullable=False),
        sa.Column(
            "decided_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("source_import_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "decision IN ('confirmed_distinct', 'confirmed_duplicate')",
            name="ck_transaction_dedup_decisions_decision",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_transaction_dedup_decisions_workspace_account",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "existing_transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="CASCADE",
            name="fk_transaction_dedup_decisions_workspace_transaction",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_import_id"],
            ["imports.workspace_id", "imports.id"],
            ondelete="SET NULL",
            name="fk_transaction_dedup_decisions_workspace_import",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "financial_account_id",
            "existing_transaction_id",
            "new_fingerprint",
            name="uq_transaction_dedup_decisions_pair",
        ),
    )
    op.create_index(
        "ix_transaction_dedup_decisions_workspace_id", "transaction_dedup_decisions", ["workspace_id"]
    )
    op.create_index(
        "ix_transaction_dedup_decisions_financial_account_id",
        "transaction_dedup_decisions",
        ["financial_account_id"],
    )

    # --- transaction_review_items --------------------------------------------

    op.create_table(
        "transaction_review_items",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("financial_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_index", sa.Integer, nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("value_date", sa.Date, nullable=True),
        sa.Column("description_raw", sa.String, nullable=False),
        sa.Column("description_normalized", sa.String, nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("direction", sa.String, nullable=False),
        sa.Column("transaction_type", sa.String, nullable=False),
        sa.Column("source_type_raw", sa.String, nullable=True),
        sa.Column("reference", sa.String, nullable=True),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=True),
        sa.Column("counterparty_name", sa.String, nullable=True),
        sa.Column("counterparty_iban", sa.String, nullable=True),
        sa.Column("new_fingerprint", sa.String(64), nullable=False),
        sa.Column("candidate_existing_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("auto_resolved", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "dedup_decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transaction_dedup_decisions.id"),
            nullable=True,
        ),
        sa.Column("resolved_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "decided_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed_new', 'confirmed_duplicate')",
            name="ck_transaction_review_items_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "import_id"],
            ["imports.workspace_id", "imports.id"],
            ondelete="CASCADE",
            name="fk_transaction_review_items_workspace_import",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_transaction_review_items_workspace_account",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "candidate_existing_transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="SET NULL",
            name="fk_transaction_review_items_workspace_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "resolved_transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="SET NULL",
            name="fk_transaction_review_items_workspace_resolved",
        ),
    )
    op.create_index("ix_transaction_review_items_workspace_id", "transaction_review_items", ["workspace_id"])
    op.create_index("ix_transaction_review_items_import_id", "transaction_review_items", ["import_id"])
    op.create_index(
        "ix_transaction_review_items_financial_account_id",
        "transaction_review_items",
        ["financial_account_id"],
    )
    op.create_index(
        "ix_transaction_review_items_import_status",
        "transaction_review_items",
        ["workspace_id", "import_id", "status"],
    )

    # --- RLS -----------------------------------------------------------------

    for table in ("transaction_dedup_decisions", "transaction_review_items"):
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

    # --- imports: contatori di report ---------------------------------------

    op.add_column(
        "imports",
        sa.Column("transactions_duplicate", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "imports",
        sa.Column("transactions_review_pending", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

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

    op.drop_column("imports", "transactions_review_pending")
    op.drop_column("imports", "transactions_duplicate")

    for table in ("transaction_review_items", "transaction_dedup_decisions"):
        for policy in ("select", "insert", "update", "delete"):
            op.execute(f"DROP POLICY IF EXISTS {table}_{policy} ON {table}")

    op.drop_table("transaction_review_items")
    op.drop_table("transaction_dedup_decisions")

    op.drop_index("ix_transactions_dedup_core_key", table_name="transactions")
    op.drop_index("ix_transactions_workspace_account_fingerprint", table_name="transactions")
    op.execute("REVOKE UPDATE (dedup_fingerprint) ON transactions FROM lumio_rls_helper")
    op.drop_column("transactions", "dedup_fingerprint")

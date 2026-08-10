"""users, workspaces, workspace_members + RLS

Revision ID: 0002_users_workspaces
Revises: 0001_initial_empty
Create Date: 2026-08-10

Milestone 02 — Auth + Multi-tenancy + RLS.

`users` non ha RLS: e' la tabella di lookup usata dal login-by-email, che
avviene prima che esista un'identita' autenticata (nessun app.current_user_id
disponibile). L'isolamento su `users` resta applicativo (ogni endpoint scopa
sempre sull'utente corrente, non esiste un "list users").

`workspaces`/`workspace_members` hanno RLS con FORCE: il ruolo applicativo
(lumio_app) e' anche il proprietario delle tabelle (le crea via migration),
e Postgres esenta di default il proprietario dalla RLS — senza FORCE la
protezione sarebbe solo apparente.

La funzione `is_workspace_member` e' SECURITY DEFINER, di proprieta' del
ruolo `lumio_rls_helper` (BYPASSRLS, creato dall'init script Postgres): serve
a evitare la ricorsione, perche' la policy su `workspace_members` altrimenti
dovrebbe interrogare `workspace_members` stessa sotto RLS per decidere se
mostrare la riga. Un proprietario "normale" non basta: con FORCE ROW LEVEL
SECURITY anche il proprietario della tabella e' soggetto alla RLS, quindi
serve un ruolo con l'attributo BYPASSRLS vero e proprio, che FORCE non
puo' annullare.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_users_workspaces"
down_revision: Union[str, None] = "0001_initial_empty"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "workspaces",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "workspace_members",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_workspace_members_role"),
    )

    # --- Row-Level Security -------------------------------------------------

    op.execute(
        """
        CREATE FUNCTION is_workspace_member(p_workspace_id uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM workspace_members
                WHERE workspace_id = p_workspace_id
                  AND user_id = current_setting('app.current_user_id', true)::uuid
            );
        $$;
        """
    )
    op.execute("ALTER FUNCTION is_workspace_member(uuid) OWNER TO lumio_rls_helper")
    # BYPASSRLS esenta lumio_rls_helper dalle *policy*, ma non sostituisce i
    # normali GRANT: senza questo, la funzione non avrebbe comunque i
    # privilegi di base per leggere la tabella.
    op.execute("GRANT SELECT ON workspace_members TO lumio_rls_helper")

    # Serve anche per il WITH CHECK di workspace_members: senza questo helper,
    # verificare "sto entrando in un workspace che possiedo davvero" dovrebbe
    # leggere `workspaces`, che ha la sua RLS — e appena dopo aver creato un
    # workspace non esiste ancora nessuna riga in workspace_members che provi
    # la mia appartenenza, quindi quella lettura tornerebbe vuota (lo stesso
    # problema di bootstrap circolare risolto sopra per is_workspace_member).
    op.execute(
        """
        CREATE FUNCTION is_workspace_owner(p_workspace_id uuid)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM workspaces
                WHERE id = p_workspace_id
                  AND owner_user_id = current_setting('app.current_user_id', true)::uuid
            );
        $$;
        """
    )
    op.execute("ALTER FUNCTION is_workspace_owner(uuid) OWNER TO lumio_rls_helper")
    op.execute("GRANT SELECT ON workspaces TO lumio_rls_helper")

    # Policy separate per comando (non un'unica FOR ALL) per chiarezza. Ma
    # attenzione: quando un INSERT ha una clausola RETURNING (SQLAlchemy la
    # aggiunge sempre, per rileggere i default generati dal server), Postgres
    # applica ANCHE la policy di SELECT alla riga appena inserita, per
    # decidere se puo' essere restituita — non solo la WITH CHECK dell'INSERT.
    # Il proprietario di un workspace appena creato non e' ancora "membro"
    # secondo is_workspace_member (quella riga in workspace_members non
    # esiste ancora), quindi la SELECT USING deve riconoscere esplicitamente
    # anche il proprietario, non solo i membri effettivi.
    # Nessuna policy UPDATE/DELETE per ora: con RLS+FORCE attivi e nessuna
    # policy per quei comandi, Postgres nega tutto di default — corretto,
    # visto che nessun endpoint li usa ancora in questa milestone.
    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspaces FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY workspaces_select ON workspaces FOR SELECT
        USING (
            is_workspace_member(id)
            OR owner_user_id = current_setting('app.current_user_id', true)::uuid
        );
        """
    )
    op.execute(
        """
        CREATE POLICY workspaces_insert ON workspaces FOR INSERT
        WITH CHECK (owner_user_id = current_setting('app.current_user_id', true)::uuid);
        """
    )

    op.execute("ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_members FORCE ROW LEVEL SECURITY")
    # Come sopra: la RETURNING dell'INSERT innesca la SELECT USING sulla riga
    # appena inserita. is_workspace_member(workspace_id) e' STABLE e la sua
    # query interna puo' non vedere ancora, all'interno dello stesso comando,
    # la riga che l'INSERT esterno sta inserendo proprio ora (visibilita' di
    # snapshot). Un controllo diretto sulla riga stessa (user_id = self) non
    # ha questo problema — ed e' comunque corretto che chiunque possa sempre
    # vedere la propria riga di membership.
    op.execute(
        """
        CREATE POLICY workspace_members_select ON workspace_members FOR SELECT
        USING (
            is_workspace_member(workspace_id)
            OR user_id = current_setting('app.current_user_id', true)::uuid
        );
        """
    )
    op.execute(
        """
        CREATE POLICY workspace_members_insert ON workspace_members FOR INSERT
        WITH CHECK (
            user_id = current_setting('app.current_user_id', true)::uuid
            AND is_workspace_owner(workspace_id)
        );
        """
    )
    # Nota per le prossime milestone: la WITH CHECK sopra permette solo di
    # auto-iscriversi come membro di un workspace che si possiede (il flow
    # "creo il mio workspace personale, poi mi aggiungo come owner"). Invitare
    # UN ALTRO utente in un workspace (family workspace, SPEC §6) richiedera'
    # una policy dedicata più permissiva, non ancora nello scope della V1.


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workspace_members_insert ON workspace_members")
    op.execute("DROP POLICY IF EXISTS workspace_members_select ON workspace_members")
    op.execute("DROP POLICY IF EXISTS workspaces_insert ON workspaces")
    op.execute("DROP POLICY IF EXISTS workspaces_select ON workspaces")
    op.execute("DROP FUNCTION IF EXISTS is_workspace_owner(uuid)")
    op.execute("DROP FUNCTION IF EXISTS is_workspace_member(uuid)")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

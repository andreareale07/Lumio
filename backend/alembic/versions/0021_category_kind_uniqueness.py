"""categories: colonna kind (tassonomia con natura del movimento) + unicita' del code

Revision ID: 0021_category_kind_uniqueness
Revises: 0020_system_settings
Create Date: 2026-08-16

Rework tassonomia categorie (vedi app/classification/taxonomy.py e il piano
di migrazione allegato). Questa migration e' SOLO schema — il reseed dei
dati (le ~180 righe della nuova tassonomia) vive nella migration successiva
0022_category_taxonomy_reseed, cosi' i due passi hanno fallimenti
indipendenti e un downgrade piu' facile da ragionare.

1) `kind` denormalizzato su ogni riga (non derivato con un self-join): il
   filtro per kind va fatto in ogni query sensibile (pipeline AI, analytics,
   picker, future pagine di dettaglio KPI) — un self-join si paga ad ogni
   query nuova per sempre, un trigger di poche righe si paga una volta sola.
   VARCHAR+CHECK per coerenza con transaction_type/direction/method (un enum
   PG richiederebbe ALTER TYPE ... ADD VALUE, non transazionale, per essere
   esteso in futuro). server_default='expense' rende l'ADD COLUMN NOT NULL
   istantaneo su tabella gia' popolata (PG11+) e da' un default sensato alle
   categorie custom esistenti dell'utente.

2) Due trigger SECURITY DEFINER (stesso pattern e stesso owner
   lumio_rls_helper di check_transaction_category_workspace, 0003):
   - enforce_category_kind: un figlio (parent_id NOT NULL) eredita SEMPRE il
     kind del padre all'INSERT/UPDATE, anche se il client ne propone uno
     diverso — l'API valida e restituisce 422 PRIMA di arrivare qui, questo
     trigger e' la seconda rete di sicurezza (CLAUDE.md: isolamento/vincoli
     critici sempre a doppio livello, applicativo + DB).
   - cascade_category_kind: un cambio di kind su una radice si propaga ai
     figli. Nessuna ricorsione da gestire: profondita' fissa a 2, quindi
     l'UPDATE che il trigger lancia sui figli non ha mai altri figli da
     propagare a sua volta.

3) Un terzo trigger, check_category_code_not_shadowing_system, chiude un
   buco che nessun indice puo' esprimere da solo: workspace_id nullable
   rompe il classico UNIQUE(workspace_id, code) perche' NULL non collide mai
   con se stesso, quindi un workspace potrebbe altrimenti creare un code
   identico a una categoria di sistema esistente (es. "casa") senza che
   nulla lo impedisca.

4) Dedup dei code duplicati gia' presenti nel DB PRIMA di creare gli indici
   unici (altrimenti la CREATE INDEX fallirebbe su un DB reale con dati):
   rinomina SEMPRE il perdente (created_at/id piu' recenti), MAI fonde due
   categorie — fondere sposterebbe silenziosamente transazioni reali tra
   categorie diverse, mentre rinominare e' lossless perche' nulla ha una FK
   su `code` (le FK del dominio puntano sempre a `categories.id`).

5) Le DML di questa migration (la UPDATE di dedup) girano sotto
   `SET LOCAL ROLE lumio_rls_helper`: le migration girano come `lumio_app`
   (utente applicativo, NOSUPERUSER NOBYPASSRLS — vedi alembic/env.py e
   .env.example) e `categories` ha FORCE ROW LEVEL SECURITY (0003), quindi
   una UPDATE scritta senza bypass non fallirebbe: aggiornerebbe SEMPRE 0
   righe, in silenzio. `lumio_rls_helper` ha gia' pieno DML su `categories`
   dal GRANT di 0003 — nessun nuovo GRANT necessario qui, solo `SET
   ROLE`/`RESET ROLE` attorno alla UPDATE, con verifica esplicita del
   conteggio finale per non fidarsi ciecamente del "0 righe aggiornate =
   nessun duplicato" (potrebbe voler dire anche "RLS ha bloccato tutto").
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021_category_kind_uniqueness"
down_revision: Union[str, None] = "0020_system_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1) colonna kind + CHECK ------------------------------------------------

    op.execute(
        "ALTER TABLE categories ADD COLUMN kind VARCHAR NOT NULL DEFAULT 'expense'"
    )
    op.execute(
        "ALTER TABLE categories ADD CONSTRAINT ck_categories_kind "
        "CHECK (kind IN ('expense', 'income', 'transfer', 'investment', 'neutral'))"
    )

    # --- 2a) enforce_category_kind: un figlio eredita SEMPRE il kind del padre -

    op.execute(
        """
        CREATE FUNCTION enforce_category_kind()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        BEGIN
            IF NEW.parent_id IS NOT NULL THEN
                SELECT kind INTO NEW.kind FROM categories WHERE id = NEW.parent_id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute("ALTER FUNCTION enforce_category_kind() OWNER TO lumio_rls_helper")
    op.execute(
        """
        CREATE TRIGGER trg_enforce_category_kind
        BEFORE INSERT OR UPDATE OF parent_id, kind ON categories
        FOR EACH ROW EXECUTE FUNCTION enforce_category_kind();
        """
    )

    # --- 2b) cascade_category_kind: un cambio di kind su una radice si propaga -
    # ai figli (profondita' fissa a 2: nessuna ricorsione da gestire, i figli
    # non hanno mai figli propri).

    op.execute(
        """
        CREATE FUNCTION cascade_category_kind()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        BEGIN
            UPDATE categories SET kind = NEW.kind WHERE parent_id = NEW.id AND kind <> NEW.kind;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute("ALTER FUNCTION cascade_category_kind() OWNER TO lumio_rls_helper")
    op.execute(
        """
        CREATE TRIGGER trg_cascade_category_kind
        AFTER UPDATE OF kind ON categories
        FOR EACH ROW
        WHEN (OLD.kind IS DISTINCT FROM NEW.kind)
        EXECUTE FUNCTION cascade_category_kind();
        """
    )

    # --- 3) dedup dei code duplicati preesistenti, PRIMA degli indici unici ----
    # (SET ROLE necessario: vedi punto 5 del docstring di modulo).

    op.execute("SET LOCAL ROLE lumio_rls_helper")
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY COALESCE(workspace_id::text, 'system'), code
                       ORDER BY created_at ASC, id ASC
                   ) AS rn
            FROM categories
        )
        UPDATE categories c
        SET code = c.code || '_' || left(c.id::text, 8)
        FROM ranked r
        WHERE c.id = r.id AND r.rn > 1
        """
    )
    op.execute(
        """
        WITH shadowing AS (
            SELECT wc.id
            FROM categories wc
            JOIN categories sc ON sc.workspace_id IS NULL AND sc.code = wc.code
            WHERE wc.workspace_id IS NOT NULL
        )
        UPDATE categories c
        SET code = c.code || '_' || left(c.id::text, 8)
        FROM shadowing s
        WHERE c.id = s.id
        """
    )
    op.execute("RESET ROLE")

    # Difesa esplicita contro il no-op silenzioso di RLS (docstring punto 5):
    # se qualche duplicato o shadowing fosse sopravvissuto, la CREATE INDEX
    # sotto fallirebbe comunque con un errore chiaro — questo blocco anticipa
    # l'errore con un messaggio che nomina esplicitamente la causa piu'
    # probabile (RLS silenziosa) invece di un generico "duplicate key value".
    connection = op.get_bind()
    duplicate_codes = connection.execute(
        sa.text(
            """
            SELECT COALESCE(workspace_id::text, 'system') AS scope, code, count(*)
            FROM categories
            GROUP BY 1, 2
            HAVING count(*) > 1
            """
        )
    ).fetchall()
    if duplicate_codes:
        raise RuntimeError(
            "Dedup dei code categoria non riuscito: duplicati residui "
            f"{duplicate_codes!r}. Se la UPDATE precedente ha aggiornato 0 righe "
            "nonostante duplicati noti, verificare che 'SET LOCAL ROLE "
            "lumio_rls_helper' sia stato applicato correttamente (vedi "
            "docstring di modulo, punto 5: RLS su categories puo' rendere una "
            "UPDATE un no-op silenzioso)."
        )

    # --- 4) trigger anti-shadowing (dopo il dedup, sui dati gia' puliti) -------

    op.execute(
        """
        CREATE FUNCTION check_category_code_not_shadowing_system()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        BEGIN
            IF NEW.workspace_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM categories
                WHERE workspace_id IS NULL AND code = NEW.code AND id <> NEW.id
            ) THEN
                RAISE EXCEPTION 'code % is reserved by a system category', NEW.code
                    USING ERRCODE = 'unique_violation';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "ALTER FUNCTION check_category_code_not_shadowing_system() OWNER TO lumio_rls_helper"
    )
    op.execute(
        """
        CREATE TRIGGER trg_check_category_code_not_shadowing_system
        BEFORE INSERT OR UPDATE OF code, workspace_id ON categories
        FOR EACH ROW EXECUTE FUNCTION check_category_code_not_shadowing_system();
        """
    )

    # --- 5) indici unici parziali (dati gia' deduplicati sopra) -----------------

    op.execute(
        "CREATE UNIQUE INDEX uq_categories_system_code ON categories (code) "
        "WHERE workspace_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_categories_workspace_code ON categories (workspace_id, code) "
        "WHERE workspace_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_categories_workspace_code")
    op.execute("DROP INDEX IF EXISTS uq_categories_system_code")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_check_category_code_not_shadowing_system ON categories"
    )
    op.execute("DROP FUNCTION IF EXISTS check_category_code_not_shadowing_system()")

    op.execute("DROP TRIGGER IF EXISTS trg_cascade_category_kind ON categories")
    op.execute("DROP FUNCTION IF EXISTS cascade_category_kind()")

    op.execute("DROP TRIGGER IF EXISTS trg_enforce_category_kind ON categories")
    op.execute("DROP FUNCTION IF EXISTS enforce_category_kind()")

    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS ck_categories_kind")
    op.execute("ALTER TABLE categories DROP COLUMN IF EXISTS kind")
    # I code rinominati dal dedup NON vengono ripristinati ai valori
    # originali (lossy, dichiarato in cima al file): nessuna FK dipende da
    # `code`, quindi la sola conseguenza e' un code diverso da quello
    # pre-migration per le righe che erano duplicate — mai una perdita di
    # dati applicativi (transazioni/regole/classificazioni puntano sempre a
    # `id`, mai a `code`).

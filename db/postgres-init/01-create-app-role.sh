#!/bin/sh
# Eseguito automaticamente da docker-entrypoint-initdb.d SOLO alla prima
# inizializzazione del data directory di Postgres, come utente bootstrap
# (POSTGRES_USER, che l'immagine ufficiale crea sempre come superuser).
#
# Crea un ruolo applicativo separato, NON superuser e senza BYPASSRLS: e'
# quello che l'app usa davvero a runtime (DATABASE_URL). Senza questo
# passaggio la Row-Level Security sarebbe puramente decorativa, perche'
# superuser/BYPASSRLS ignorano sempre le policy, anche con FORCE ROW LEVEL
# SECURITY sulle tabelle.
#
# Crea anche `lumio_rls_helper`, NOLOGIN ma con BYPASSRLS: serve come
# proprietario delle funzioni SECURITY DEFINER usate dentro le policy (es.
# is_workspace_member) per leggere una tabella senza applicarne la RLS su se
# stessa — altrimenti la policy dovrebbe valutare la RLS della stessa tabella
# per decidere se applicare la RLS della stessa tabella, andando in ricorsione.
# Un ruolo owner-ma-non-BYPASSRLS non basta: FORCE ROW LEVEL SECURITY toglie
# l'esenzione anche al proprietario, quindi qui serve BYPASSRLS vero, che
# FORCE non puo' annullare.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${POSTGRES_APP_USER}') THEN
            CREATE ROLE "${POSTGRES_APP_USER}"
                WITH LOGIN PASSWORD '${POSTGRES_APP_PASSWORD}'
                NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
        END IF;

        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lumio_rls_helper') THEN
            CREATE ROLE lumio_rls_helper
                WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;
        END IF;
    END
    \$\$;

    GRANT lumio_rls_helper TO "${POSTGRES_APP_USER}";
    GRANT ALL PRIVILEGES ON DATABASE "${POSTGRES_DB}" TO "${POSTGRES_APP_USER}";
    GRANT ALL ON SCHEMA public TO "${POSTGRES_APP_USER}";
    -- ALTER FUNCTION ... OWNER TO lumio_rls_helper richiede che il NUOVO
    -- proprietario abbia CREATE sullo schema della funzione, non solo chi
    -- esegue l'ALTER.
    GRANT CREATE ON SCHEMA public TO lumio_rls_helper;
EOSQL

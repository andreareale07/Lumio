# Progetto: database PostgreSQL e Row-Level Security

## Ruoli (perche' sono due)
- `lumio_app`: ruolo di runtime usato da `DATABASE_URL`, `NOSUPERUSER NOBYPASSRLS`. Un
  superuser ignora sempre la RLS: mai puntare l'app al superuser.
- `lumio_rls_helper`: `NOLOGIN BYPASSRLS`, concesso a `lumio_app`. Owner delle funzioni
  `SECURITY DEFINER` e usato (con `SET ROLE`) per reseed di dati di sistema nei test.
  **BYPASSRLS non da' privilegi sulle tabelle**: ogni uso richiede un `GRANT` esplicito
  (es. SELECT su `transactions`, INSERT su `workspace_members` - migration 0014).
- Creati da `db/postgres-init/01-create-app-role.sh` solo al primo avvio del volume; su un
  Postgres esterno vanno creati a mano (istruzioni in testa a `docker-compose.external-db.yml`).
- Identita': `SET LOCAL app.current_user_id` via `app/db/rls.py`. Le policy fanno cast
  `::uuid`: se l'identita' manca l'errore tipico e' `invalid input syntax for type uuid: ""`.

## Pattern obbligatorio per una tabella nuova con dati di workspace
`ENABLE` + `FORCE ROW LEVEL SECURITY` + **4 policy separate** SELECT/INSERT/UPDATE/DELETE
+ test RLS dedicato (`tests/test_rls_*.py`, 4 comandi x tabella).
- FK verso una tabella di workspace mai nullable: FK **composita** `(workspace_id, id)` verso
  `UNIQUE(workspace_id, id)`.
- FK nullable che puo' puntare a righe di sistema (`workspace_id NULL`): Postgres **non
  applica la RLS della tabella referenziata nel controllo FK** -> serve un trigger
  `BEFORE INSERT OR UPDATE` con funzione `SECURITY DEFINER` (modello:
  `check_transaction_category_workspace()` in `alembic/versions/0003_accounts_transactions.py`).
- Dati "globali" di mercato (es. `fx_rates`) senza `workspace_id` ne' RLS. `asset_prices`
  invece e' per workspace: gap noto e accettato (vedi `guida-investimenti-e-fiscalita.md`).

## Insidie (ognuna gia' costata ore)
1. **`SET LOCAL` scade al commit** - ricaduto 5+ volte (`imports.py`, `accounts.py`,
   `tax.py`, `live_quote_service.py`, `detection.py`, job `market_data.py`).
   Euristica di revisione: per ogni `await db.commit()` controllare se dopo, nella stessa
   funzione o nel chiamante, c'e' un'altra query RLS. Rimedi: commit unico a fine
   richiesta; `flush()` -> `refresh()` -> `commit()`; costruire la response prima del commit;
   in ultima istanza richiamare `set_rls_current_user`. Prima di scrivere
   `db.refresh(x)` dopo un commit: con `eager_defaults=True` quasi sempre non serve.
2. **Bulk `update()` non aggiorna l'identity map** ORM: aggiornare in bulk solo le altre
   righe (`WHERE id != :target`) e mutare l'attributo dell'oggetto gia' caricato (modello:
   `ai_profile_service.py::activate_profile`).
3. **Test RLS falsamente verdi**: con zero righe che matchano, Postgres non invoca la policy
   e il cast fallito non scatta. Un test RLS-sensibile deve creare almeno una riga reale
   che la query leggerebbe (es. una `Position`, non solo l'`Asset`).
4. **Migration con UPDATE/DELETE/backfill sotto FORCE RLS** vede zero righe senza errore.
   Soluzione usata (0041/0043): `ALTER TABLE t NO FORCE ROW LEVEL SECURITY; <pulizia>;
   ALTER TABLE t FORCE ROW LEVEL SECURITY;` nella stessa transazione. Provare **sempre** il
   downgrade con almeno una riga reale (a tabella vuota sembra funzionare).
5. Colonna NOT NULL nuova su `transactions` rompe gli INSERT SQL raw nei `test_rls_*.py`
   esistenti: aggiornarli.
6. `TRUNCATE ... CASCADE` svuota anche le righe di sistema (categorie con
   `workspace_id NULL`): `tests/conftest.py` le reinserisce con `SET ROLE lumio_rls_helper`.

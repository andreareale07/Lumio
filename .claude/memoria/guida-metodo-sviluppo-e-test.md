# Guida: metodo di sviluppo e test

## Ciclo di lavoro
Si lavora per milestone/fette verificabili (`docs/ROADMAP.md`):
analisi di cio' che esiste -> piano (DECISION REQUIRED se manca un requisito importante)
-> implementazione dell'**intera fetta** -> verifica una sola volta a fine fetta -> commit
**solo su richiesta**.
- Niente test dopo ogni singolo file: costa token e tempo (la suite pytest completa dura
  10-17 minuti). Sono ammessi controlli puntuali solo per diagnosticare un bug appena
  introdotto o per una modifica ad alto rischio isolata (es. SQL mai provato).
- Le fette piccole sono preferite ("titoli delle 8 pagine Impostazioni", non "tutte le
  Impostazioni").
- La verifica reale resta obbligatoria per le feature visibili all'utente: quasi tutti i bug
  gravi (RLS a meta' richiesta, `_job_id` di arq, grafici duplicati su Google, compensazione
  fiscale non causale) li hanno trovati il QA manuale o l'utente, non i test.
- Ogni milestone visibile all'utente include il frontend (loading/error/empty state,
  responsive, test). In caso di conflitto, `docs/SPEC.md` prevale su `docs/SPEC_FE.md`.

## Livelli di verifica (dal piu' economico)
| Livello | Cosa | Comando |
|---|---|---|
| STATICO | lint + tipi | `ruff check .` · `npm run lint` · `npx tsc -b` |
| BUILD | build frontend | `npm run build` (warning dimensione bundle preesistente) |
| UNIT | vitest, test `*_calc` puri | `npm run test` · `pytest tests/test_x_calc.py` |
| DB | pytest con Postgres/Redis **effimeri** | vedi sotto |
| HTTP | curl contro lo stack Docker | `curl localhost:8000/health` e `/ready` |
| BROWSER | flusso reale nell'app | stack Docker su :5173 con browser integrato |
| CI | GitHub Actions `.github/workflows/ci.yml` | gira a ogni push |

## pytest: solo container effimeri
**Mai** puntare pytest al DB `lumio` dello stack Docker: `tests/conftest.py::_clean_tables`
fa `TRUNCATE ... CASCADE` prima di ogni test (ha gia' cancellato i dati di verifica
dell'utente). Stesso setup di `ci.yml`, su porte diverse da 5432/6379:
1. `docker run --rm -d --name lumio-ci-pg -e POSTGRES_USER=ci_admin -e POSTGRES_PASSWORD=... -e POSTGRES_DB=lumio -p 5433:5432 postgres:16-alpine`
   e `docker run --rm -d --name lumio-ci-redis -p 6380:6379 redis:7-alpine`
2. Attendere `pg_isready`, poi creare `lumio_app` e `lumio_rls_helper` con lo stesso SQL
   dello step "Create non-superuser app role" di `ci.yml`, usando
   `docker exec -i ... psql ... <<EOSQL` (**`-i` obbligatorio**, altrimenti l'heredoc viene
   ignorato senza errori).
3. Env inline: `DATABASE_URL` (ruolo `lumio_app`, porta 5433), `REDIS_URL` (6380),
   `SECRET_KEY`, e anche `GOOGLE_ENABLED=true` + `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`
   fittizi, altrimenti i 9 test di `test_integrations_google_api.py` falliscono (404).
4. `alembic upgrade head`, poi `pytest`. Infine `docker stop` dei due container.
- Non incanalare l'output di run lunghi in `| tail` (sembra bloccato fino a EOF): usare
  `PYTHONUNBUFFERED=1` e `-q`.

## Falsi verdi su Windows
Un run verde su Windows non garantisce la CI: `/app/storage` diventa `C:/app/storage`
(scrivibile), mentre su Linux senza privilegi no. Per validare un commit critico per la
CI, riprodurre il job in un container Linux con uid non privilegiato (`docker exec -u 1001`).
In Git Bash: `MSYS_NO_PATHCONV=1` per i path `-w /w`, ma il sorgente di `docker cp` va in
forma Windows (`C:/Progetti/...`). Se si copia solo `backend/`, `test_categories_i18n.py`
fallisce (cerca `frontend/src/locales`): non e' un errore reale.

## Stack Docker locale: insidie
- Il codice e' **dentro l'immagine** (nessun bind-mount): dopo una modifica,
  `docker compose build <servizio> && docker compose up -d <servizio>`. Un `restart` non
  basta.
- Dopo il rebuild di `app`/`worker`: `docker compose restart frontend` (nginx conserva il
  vecchio IP del backend -> 502).
- Build del frontend stantia su :5173: controllare l'hash con
  `curl -s localhost:5173/ | grep assets/index-`; nel browser usare una tab nuova o `?bust=N`.
- Playwright (`reuseExistingServer: !CI`) riusa qualunque server su :5173, anche la build
  Docker vecchia. Su Windows IPv4 e IPv6 possono convivere sulla stessa porta senza errori.
  Prima di `npm run test:e2e`: `docker stop lumio-frontend-1`, poi rimetterlo su.
- Gli E2E testano implicitamente anche la pipeline di classificazione (merchant extraction):
  le asserzioni sui testi delle descrizioni sono fragili.
- Browser integrato: se un click su un submit non genera richieste, usare
  `requestSubmit()` via JavaScript.
- Rate limit di registrazione: troppe chiamate manuali rendono rumorosi gli E2E.

## Dati di test
- Nei test e nelle fixture **solo dati sintetici** (societa', persone, IBAN inventati) che
  riproducono la struttura del caso reale (commit `5b0d108`).
- Verifiche manuali nel browser su account di test dedicati (`*-verify@example.com`), mai
  modificando l'account reale dell'utente. Sui dati reali sono ammesse solo letture (GET).

## Prima del commit
STATICO + UNIT + DB sulla fetta (la suite completa se si tocca codice condiviso o
RLS), rebuild Docker e prova nel browser per le modifiche visibili, nessun file di
debug/temporaneo, messaggio secondo `procedura-gestione-branch.md`.

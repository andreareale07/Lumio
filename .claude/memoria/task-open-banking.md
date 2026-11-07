# Task: Open Banking (Enable Banking), sviluppato il 2026-11-06 (non committato al 2026-11-06)

Guide per l'utente: `docs/open-banking-setup.md` (installazione e produzione), `-costs.md`, `-coverage.md`.

## Vincolo contrattuale (decide l'architettura)
I Terms di Enable Banking (2026-01-09, https://enablebanking.com/terms/) rendono la produzione **gratuita solo per uso personale con
conti propri**; vietano credenziali condivise, conti aziendali e di terzi. Quindi: application ID + chiave RSA **per utente**
(`open_banking_credentials`, RLS **owner-only**, anche rispetto agli altri membri del workspace), mai credenziali d'istanza in `.env`.
La chiave la genera Lumio (`openbanking/keys.py`), cifrata con `core/crypto.py` (Fernet da `SECRET_KEY`: se cambia, vanno rigenerate).
Il numero massimo di conti per applicazione e il comportamento reale delle banche **non sono verificati** (nessun test con conti reali).

## Dove sta il codice
- Backend: `app/openbanking/` (Protocol `BankConnector`, `enable_banking.py`, `state.py`, `keys.py`), `models/open_banking.py`,
  `services/open_banking_service.py` + `bank_sync_service.py` + `import_deletion.py`, `api/v1/open_banking.py`, `worker/jobs/bank_sync_job.py`.
  Migration `0044_open_banking`. Flag `OPEN_BANKING_ENABLED` (router montato una sola volta all'import, come Google) e
  `MeResponse.open_banking_enabled` (3 punti in `auth.py`).
- Frontend: `features/settings/open-banking/` (pagina `/settings/bank-connections`), avviso globale `BankConnectionsNotice` in `AppShell`.
- Decisioni UI da mockup a confronto (2026-11-06): configurazione a un passo per schermata; scelta banca in `BottomSheet` su
  smartphone (Dialog su desktop); conti da importare uno per volta con dialog di abbinamento; elenco banche compatto espandibile;
  **una sola riga di stato** per banca che diventa il pulsante d'azione ("Rinnova"/"Riprova"); barra d'avviso in tutta l'app
  (nascosta nella pagina stessa); scollegamento in foglio con riepilogo dell'impatto + casella "elimina anche i movimenti".

## Scelte non ovvie
- Ogni sync crea un `Import` con `file_type='open_banking'` e passa da `_insert_transactions_and_complete` (dedup, REVIEW,
  classificazione, trasferimenti): `external_id` della banca come chiave primaria, fingerprint come rete di sicurezza.
- Solo movimenti **BOOK** (i pending non hanno id stabile). Primo giro `strategy=longest`, poi `last_booked_date - 7 giorni`.
- Stato della sync **per connessione** (`bank_connections.last_sync_at/last_error`), NON in `job_runs`: nessun nuovo job_kind.
  Lock e backoff su Redis (`bank_sync:lock:*`, `bank_sync:attempt:*`); intervallo minimo 6 ore (limite ~4 letture/giorno senza utente).
- Il cron non ha identita' RLS: usa `list_active_bank_connections()` (SECURITY DEFINER + GRANT SELECT a `lumio_rls_helper`).
- `bank_connection_accounts.financial_account_id`: FK composita con `ON DELETE SET NULL (financial_account_id)` (PG >= 15), altrimenti
  azzererebbe anche `workspace_id`.
- Scollegare con `delete_data=true` elimina solo i movimenti degli `Import` open_banking sui conti abbinati (mai PDF/CSV/manuali);
  logica condivisa con `DELETE /imports/{id}` in `services/import_deletion.py`. 409 se un import e' in corso.
- Rinnovo = nuova connessione: eredita abbinamenti e cursore per IBAN e ritira la precedente (molte banche italiane: un solo consenso).

## Insidie incontrate
- `Dialog` rimette il focus sul primo campo a ogni render se cambia l'identita' di `onClose`: passare callback **stabili** (`useCallback`)
  ai dialog con campi (la ricerca banche perdeva il focus).
- `Card` + `p-0` non vince sul `p-4` di default (ordine del foglio Tailwind): per un contenitore senza padding usare un `div`.
- Test: `OPEN_BANKING_ENABLED=true` e `OPEN_BANKING_REDIRECT_URI` vanno in env prima di pytest; in CI sono in `ci.yml`.
- Verifica nel browser senza toccare i dati reali: backend su porta 8010 + worker + Vite su 5174 contro Postgres/Redis effimeri e un
  **mock locale dell'API del provider** (`backend/scripts/mock_enable_banking.py`, `OPEN_BANKING_BASE_URL=http://localhost:9999`). Un `fetch('/auth/refresh')` a mano
  ruota il cookie e fa perdere la sessione al reload.

## Stato verifiche (2026-11-06)
Backend: ruff pulito, suite completa 965 test verdi (prima del refactor di `import_deletion`; dopo: 144 test mirati verdi). Frontend: 278 test, lint, build ok.
Verifica manuale nel browser a 375px su DB effimeri con il mock del provider: configurazione, collegamento, abbinamento, sync (anche ripetuta),
scadenza, scollegamento con eliminazione dati. Playwright E2E non rieseguiti. Ambiente dell'utente: Lumio in HTTPS su un dominio DuckDNS,
produzione in container LXC Proxmox (CTID e percorso non noti: chiederli prima di dare comandi di aggiornamento).

## Analisi di sicurezza (2026-11-07): fatta e corretta
Report: artifact privato "Analisi sicurezza Open Banking". Verificato OK: `state` e token di accesso non intercambiabili, RLS/IDOR, nessun open
redirect, chiave privata mai in API, payload grezzo non salvato. Corretto (test in `tests/test_open_banking_security.py` e `..._state_keys.py`):
- `SECRET_KEY`: con `APP_ENV=production` l'app non parte se < 32 caratteri o segnaposto; chiavi per scopo via HKDF (`core/keys.py`):
  Fernet nuovo + **fallback in lettura sul formato storico** (`MultiFernet`), state OB firmato con chiave derivata. I JWT di accesso restano sul
  valore grezzo (cambiarli chiuderebbe le sessioni). Cambiare `SECRET_KEY` rende ancora illeggibili i segreti.
- URL del provider: `openbanking/urls.py::safe_provider_url` (solo https; http solo se la base URL e' http, cioe' il mock) per `authorize_url` e loghi;
  frontend `safeUrl.ts`; id nei percorsi validati con regex.
- Callback: nonce consumato con un solo `UPDATE ... RETURNING` (atomico, provato con 3 callback concorrenti).
- Scollegamento: prende il lock Redis della sync (409 se una sync e' in corso). Sync manuale: pausa 30 s. `/institutions`: 30/min.
- IP/UA verso la banca: solo `request.client.host` validato (`core/client_info.py`), mai `X-Forwarded-For` letto a mano; uvicorn `--proxy-headers`
  con reti private fidate; nginx `set_real_ip_from` + `X-Forwarded-For` sostituito. Access log nginx senza query, filtro uvicorn che maschera code/state.
- nginx: CSP, HSTS (se `X-Forwarded-Proto: https`), tema in `public/theme-init.js` (niente script inline); verificato nel browser su build di produzione.
- Migration 0044 (non ancora applicata al DB reale, modificata in place): funzione con `search_path` fisso, EXECUTE chiuso a PUBLIC, GRANT di colonna al helper.
- Job di sync: salta gli utenti non attivi. Compose di sviluppo: Postgres/Redis/API solo su 127.0.0.1.
Secondo giro (2026-11-07, "blindare lo scambio con l'esterno"):
- Loghi: il browser non contatta piu' il sito del provider. `openbanking/logos.py` li scarica dal server (solo https e IP pubblici, nessun redirect, max 150 KB,
  solo PNG/JPEG/WEBP/GIF dai magic bytes, mai SVG), li mette in cache Redis e li serve da `/api/v1/open-banking/logos/{key}` (chiave opaca registrata
  dall'elenco banche, mai un URL scelto dal chiamante). CSP nginx `img-src 'self' data: blob:`.
- `core/outbound.py::guarded_client`: policy SSRF per endpoint scelti dall'utente (AI Ollama/custom, market data custom): vietati link-local/metadati cloud,
  nessun redirect; LAN e localhost restano ammessi. Messaggi d'errore AI senza il corpo della risposta (canale di lettura SSRF).
- Connettore OB: tetto 20 MB alla risposta, NaN/Infinity/importi assurdi scartati, testi e date limitati, nessun redirect, in produzione la base URL deve essere
  `api.enablebanking.com` (override `OPEN_BANKING_ALLOW_CUSTOM_BASE_URL`).
- Redis: password opzionale (`REDIS_PASSWORD` + `REDIS_URL=redis://:pw@redis:6379/0`), compose con comando e healthcheck condizionali; provato con redis-py, arq e slowapi.
  Senza `REDIS_PASSWORD` nulla cambia.
- Dipendenze (2026-11-07): `pip-audit` segnalava pyjwt 2.9.0, python-multipart 0.0.12, cryptography 43.0.1, starlette 0.38.6: portati a pyjwt 2.15.1,
  python-multipart 0.0.33, cryptography 50.0.2, fastapi 0.162.0 (starlette 1.10.0); suite completa 1017 test verdi. L'immagine Docker va ricostruita per averli.
  `npm audit`: zod e source-map-js aggiornati nel lockfile, restano vite/esbuild (solo server di sviluppo, serve vite 8 major). Attenzione: `npm audit fix --omit=dev` toglie le devDependencies da
  node_modules: rilanciare `npm install`.
- Attenzione operativa: `docker compose config` STAMPA il contenuto del `.env` (interpolato): non usarlo senza filtrare.
Terzo giro (2026-11-07, dopo il commit `bcc9797`):
- `state` OPACO: non e' piu' un JWT ma un token Fernet con chiave dedicata (cifrato e autenticato, TTL 10 min): banca e provider non vedono utente/workspace.
- `guarded_client` fissa l'IP alla CONNESSIONE (`_PinnedBackend` iniettato in `transport._pool._network_backend`, attributo interno di httpx 0.27: c'e'
  un test che lo prova): chiude il DNS rebinding. `trust_env=False` (nessun proxy da variabili d'ambiente).
Non corretto (decisioni aperte): log di errore nginx con la query (non redigibile; abbassare `error_log` a `crit` toglierebbe anche la diagnostica dei 502),
CSP non provata col Picker Google, nessuna retention dei dati, vite/esbuild (solo dev server), 5 deprecazioni Starlette (`HTTP_422_UNPROCESSABLE_ENTITY` -> `..._CONTENT`).

## Non fatto / da verificare
Collegamento con conti reali (Poste, ecc.), E2E Playwright dedicati, notifica fuori dall'app (email/push), movimenti pending,
"rileggi lo storico" dopo aver eliminato un import open_banking (il cursore non riparte).

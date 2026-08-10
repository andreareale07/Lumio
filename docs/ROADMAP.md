# Lumio — Roadmap per milestone

Ogni milestone è una sessione (o poche sessioni) di lavoro autoconclusiva. Non si passa
alla milestone successiva finché quella corrente non soddisfa la Definition of Done (DoD)
generale (sezione 78 di `SPEC.md`) e quella specifica elencata qui sotto.

Convenzione: quando lavori su una milestone, dì a Claude Code esplicitamente quale
numero stai affrontando, es. "Lavoriamo sulla milestone 03 — Accounts + Transactions".

---

## 01 — Foundation

**Scope**: repository, Docker Compose (app/worker/postgres/redis), FastAPI skeleton,
React/TypeScript/Vite skeleton, Alembic inizializzato, `.env.example`, CI base,
framework di test (pytest + vitest/playwright), health checks `/health` e `/ready`.

**Riferimenti spec**: sezioni 4, 5, 61-64, 76 (Fase 0).

**DoD**:
- `docker compose up -d` avvia tutto senza errori
- Alembic applica una migration vuota di test
- `/health` e `/ready` rispondono
- CI esegue lint + test su push

---

## 02 — Auth + Multi-tenancy + RLS

**Scope**: tabella `users` con password hashing moderno, tabella `workspaces`,
`workspace_members` con ruoli (`owner`, `member`), sessioni/token sicuri,
Row-Level Security su PostgreSQL attiva su tutte le tabelle tenant-scoped.

**Riferimenti spec**: sezioni 6, 7, 13-15, 52.

**DoD**:
- register/login funzionanti end-to-end
- test automatico: `User A → risorsa di User B → DENIED`, sia a livello applicativo che via RLS
- nessuna tabella con dati tenant-scoped priva di RLS

---

## 03 — Accounts + Transactions

**Scope**: `banks` (entità globali), `financial_accounts`, `transactions` con
`description_raw`/`description_normalized` separati, `categories` gerarchiche,
transaction types completi (expense/income/transfer/investment/dividend/interest/fee/tax/refund/adjustment),
riconoscimento (anche manuale in questa fase) dei trasferimenti interni.

**Riferimenti spec**: sezioni 16, 18, 20-22.

**DoD**:
- CRUD completo su conti e transazioni con isolamento tenant verificato
- categorie di sistema (`workspace_id = NULL`) e categorie custom coesistono
- constraint DB attivi contro relazioni cross-tenant (sezione 57)

---

## 04 — Import Engine

**Scope**: modello `imports` con stati (uploaded→queued→processing→...→completed/failed),
import CSV come primo canale, `file_hash` per rilevare duplicati, job async via
Redis + worker, eventi SSE (`job.created`, `job.progress`, ecc.), UI di progresso.

**Riferimenti spec**: sezioni 19, 50, 51, 58.

**DoD**:
- import di un CSV produce transazioni corrette con job trackabile via SSE
- upload dello stesso file due volte → duplicato rilevato, nessuna doppia transazione
- nessun polling continuo lato frontend

---

## 05 — Trade Republic Parser

**Scope**: interfaccia astratta `BankParser` (`detect`/`parse`), primo parser concreto
per Trade Republic, `bank_parsers` con versionamento, integrazione nell'Import Engine
per PDF (oltre a CSV), sandboxing/validazione file (MIME, dimensione, timeout).

**Riferimenti spec**: sezioni 17, 53, 94.

**DoD**:
- PDF Trade Republic reale importato correttamente end-to-end (upload → parse → transazioni)
- parser aggiungibile senza toccare il dominio transazioni/dashboard
- file non-PDF con estensione `.pdf` rifiutato in modo sicuro

---

## 06 — Rules Engine

**Scope**: tabella `rules` con operatori (`equals`, `contains`, `starts_with`, `ends_with`,
`regex`, `merchant_equals`), valutazione delle regole prima di qualsiasi AI, tabella
`classifications` per storicizzare metodo/provider/score, UI per creare regole anche
da correzioni ripetute dell'utente ("vuoi creare una regola automatica?").

**Riferimenti spec**: sezioni 23, 24, 29.

**DoD**:
- regola creata manualmente classifica correttamente nuove transazioni in import successivi
- storico classificazioni consultabile (chi/come ha classificato ogni transazione)
- proposta automatica di regola dopo correzioni ripetute funzionante

---

## 07 — AI Abstraction

**Scope**: interfaccia `AIClassifier`, provider `NoAI` (default), `Ollama` (locale),
`OpenAI`/`Anthropic`/custom endpoint (cloud), cifratura API key a riposo, mascheramento
in UI, flusso hybrid Rules→Local AI→Cloud AI descritto in sezione 28, confidence score
applicativo (non solo quello dichiarato dal modello).

**Riferimenti spec**: sezioni 25-28, 82.

**DoD**:
- app funziona identicamente con `AI_PROVIDER=none`
- switch tra provider via configurazione, zero modifiche al dominio
- nessuna API key visibile in log, risposte API, o UI non mascherata

---

## 08 — Dashboard + Analytics

**Scope**: dashboard centrale (patrimonio, liquidità, spese, entrate, cash flow),
analytics spese/entrate (mensile, annuale, confronto periodi, per categoria/merchant),
grafici (line/area, donut, bar) interattivi, filtri coerenti (periodo, conto, categoria,
tipo, merchant, importo), empty states dedicati per ogni sezione senza dati.

**Riferimenti spec**: sezioni 30, 39, 45, 46, 73, 74.

**DoD**:
- dashboard carica in tempo utile con migliaia di transazioni (pagination/aggregazione, non tutto nel browser)
- cash flow esclude correttamente i trasferimenti interni
- ogni grafico ha un empty state sensato, non un grafico vuoto

---

## 09 — Portfolio

**Scope**: `assets`, `positions`, `investment_transactions` (buy/sell/dividend/deposit/
withdrawal/fee/tax/split), `portfolios` aggregabili su più conti, interfaccia
`MarketDataProvider` astratta (funzionante anche se non configurata), snapshot storici
per net worth e performance, analytics portfolio (allocation, P/L, performance nel tempo).

**Riferimenti spec**: sezioni 31, 32-38, 73.

**DoD**:
- posizione multi-conto aggregata correttamente in un portfolio
- app funziona anche senza market data provider configurato (nessun crash, dato assente gestito)
- storico patrimonio consultabile via snapshot, non ricalcolato da zero ogni volta

---

## 10 — Google Sheets

**Scope**: integrazione opzionale e isolata (`integrations`), OAuth Google, selezione
spreadsheet, export verso Sheets, nessuna dipendenza del resto dell'app da questa
integrazione se disabilitata.

**Riferimenti spec**: sezioni 47, 54.

**DoD**:
- con `GOOGLE_ENABLED=false` nessuna funzionalità core è impattata
- export verso Sheets rispetta i permessi del workspace
- credenziali OAuth non finiscono nei log

---

## 11 — Hardening + Security

**Scope**: audit completo di autorizzazione/RLS su tutte le entità, rate limiting,
CSRF dove necessario, validazione input, secure headers, test di sicurezza
cross-tenant su ogni tabella (sezione 56), audit log (`LOGIN`, `IMPORT_CREATED`, ecc.),
verifica che nessun secret/dato sensibile finisca nei log.

**Riferimenti spec**: sezioni 7, 52, 55, 56, 59.

**DoD**:
- suite di security test verde su tutte le entità elencate in sezione 56
- audit log popolato per le azioni elencate in sezione 59, senza dati sensibili
- nessun secret in chiaro nei log applicativi

---

## 12 — Packaging + Documentation

**Scope**: `docker-compose.yml` + `docker-compose.external-db.yml` finalizzati,
`README.md`, `ARCHITECTURE.md`, `DEVELOPMENT.md`, `DEPLOYMENT.md`, `DATABASE.md`,
`SECURITY.md`, `API.md`, `CONTRIBUTING.md`, script `backup.sh`/`restore.sh`,
verifica installazione da zero su ambiente pulito (homelab-style, CPU-only).

**Riferimenti spec**: sezioni 60-64, 80, 81.

**DoD**:
- un utente senza esperienza tecnica avvia l'app seguendo solo il README
- un power user configura PostgreSQL/Redis esterni seguendo solo DEPLOYMENT.md
- backup e restore testati almeno una volta end-to-end

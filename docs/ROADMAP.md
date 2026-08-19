# Lumio — Roadmap per milestone

Ogni milestone è una sessione (o poche sessioni) di lavoro autoconclusiva. Non si passa
alla milestone successiva finché quella corrente non soddisfa la Definition of Done (DoD)
generale (sezione 78 di `SPEC.md`) e quella specifica elencata qui sotto.

Convenzione: quando lavori su una milestone, dì a Claude Code esplicitamente quale
numero stai affrontando, es. "Lavoriamo sulla milestone 03 — Accounts + Transactions".

---

# Frontend Workstream — Regola generale

Lumio è un'applicazione full-stack.

Lo sviluppo non deve essere interpretato come:

```text
Backend → completamento → Frontend
```

ma come sviluppo coordinato di:

```text
Backend
   ↕
API / Events
   ↕
Frontend
```

Il frontend React/TypeScript è parte integrante del prodotto e deve essere sviluppato progressivamente insieme al backend.

## Regola fondamentale

**Ogni milestone deve valutare anche l'impatto sul frontend.**

Quando una milestone introduce una funzionalità utilizzabile dall'utente, la milestone deve includere:

1. implementazione backend;
2. API/eventi necessari;
3. implementazione frontend;
4. gestione loading state;
5. gestione error state;
6. gestione empty state quando applicabile;
7. gestione responsive/mobile quando applicabile;
8. test appropriati.

Non considerare una funzionalità completata se esiste solamente nel backend ma non è utilizzabile dalla UI, salvo che la milestone specifichi esplicitamente che si tratta di una componente infrastrutturale.

---

# Progressive Frontend Development

Il frontend deve evolvere progressivamente durante tutte le milestone.

Non accumulare tutto lo sviluppo UI alla fine del progetto.

La struttura concettuale è:

```text
M01
Foundation
    ↓
Frontend shell

M02
Authentication
    ↓
Login / Registration / Session UI

M03
Accounts + Transactions
    ↓
Accounts UI
Transactions UI

M04
Import Engine
    ↓
Upload UI
Import status
Progress
Errors

M05
Trade Republic Parser
    ↓
Provider detection
Import review

M06
Rules Engine
    ↓
Rules management
Classification review
User corrections

M07
AI
    ↓
AI settings
Provider configuration
Classification suggestions

M08
Dashboard
    ↓
Financial dashboard
Charts
Analytics

M09
Portfolio
    ↓
Portfolio dashboard
Positions
Allocation
Performance

M10
Google Sheets
    ↓
Integration settings
Export UI

M11
Hardening
    ↓
Security UX
Session management
Error handling

M12
Packaging
    ↓
Onboarding
Setup documentation
Production UX
```

---

# Definition of Done — Frontend

Una milestone che introduce una funzionalità utente non può essere considerata completa solamente perché:

```text
API funzionante
+
Database funzionante
```

Deve essere verificato anche:

```text
API
+
Frontend
+
User Flow
+
Error Handling
+
Loading State
+
Empty State
```

quando applicabile.

---

# User Flow First

Per ogni nuova funzionalità, Claude Code deve ragionare in termini di user flow.

Esempio:

```text
User
 ↓
Click "Importa"
 ↓
Select PDF
 ↓
Upload
 ↓
Processing
 ↓
Progress
 ↓
Completed
 ↓
Review
 ↓
Transactions
```

Non implementare solamente:

```text
POST /imports
```

senza costruire anche l'esperienza che permette all'utente di utilizzare quella API.

---

# Backend-Frontend Contract

Ogni nuova API utilizzata dalla UI deve avere un contratto chiaro.

Il contratto deve definire almeno:

* request;
* response;
* error response;
* authentication requirements;
* authorization;
* pagination quando applicabile;
* filtering quando applicabile;
* sorting quando applicabile;
* loading/asynchronous behavior quando applicabile.

Il frontend non deve dipendere da dettagli interni del backend.

---

# No Fake UI

Durante lo sviluppo non utilizzare dati fittizi nella UI per simulare funzionalità già previste dal backend, salvo che sia esplicitamente richiesto per una fase di prototipazione.

Quando il backend della funzionalità è disponibile:

```text
Frontend
   ↓
Real API
   ↓
Real database
```

deve essere utilizzato il flusso reale.

---

# UI Quality

Il frontend deve mantenere una qualità coerente con il Product Spec di Lumio.

L'interfaccia deve essere:

* moderna;
* chiara;
* responsive;
* accessibile;
* coerente;
* visualmente curata;
* prevedibile;
* priva di percorsi inutilmente complessi.

Non creare una semplice interfaccia tecnica sopra le API.

Lumio deve essere percepito come un prodotto finanziario moderno, non come un pannello amministrativo.

---

# Shared Design System

I componenti UI comuni devono essere riutilizzati.

Evitare di creare implementazioni differenti dello stesso concetto.

Esempi:

```text
Button
Input
Select
Modal
Dialog
Toast
Table
Pagination
DateRangePicker
Filter
Badge
Card
Chart
EmptyState
LoadingState
ErrorState
```

devono avere componenti condivisi quando utilizzati in più sezioni.

---

# Responsive by Default

Il frontend deve essere progettato fin dall'inizio per:

```text
Desktop
Tablet
Mobile
```

Non considerare il responsive come un'attività esclusivamente finale.

Le funzionalità principali devono essere utilizzabili anche da smartphone.

---

# Mobile Strategy

Lumio sarà inizialmente una web application responsive.

L'architettura frontend deve però essere compatibile con una futura:

```text
PWA
```

e con eventuali applicazioni native:

```text
iOS
Android
```

Le API backend devono quindi essere indipendenti dal browser.

---

# Frontend Testing

Le funzionalità importanti devono avere test frontend appropriati.

Utilizzare:

```text
Unit tests
Component tests
Integration tests
E2E tests
```

in funzione della complessità della funzionalità.

I principali user flow devono essere verificabili end-to-end.

Esempio:

```text
Login
→ Upload
→ Processing
→ Review
→ Transactions
```

---

# Milestone Completion

Prima di dichiarare completata una milestone, Claude Code deve verificare:

### Backend

* implementazione completata;
* test backend verdi;
* API funzionanti.

### Frontend

* UI implementata;
* API integrate;
* loading state;
* error state;
* empty state quando applicabile;
* responsive behavior.

### Integration

* user flow completo;
* autorizzazione verificata;
* multi-tenancy verificata;
* nessuna regressione.

Solo dopo queste verifiche la milestone può essere considerata completa.


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

## 06.5 — Frontend Integration + Core UI

**Scope**: implementazione della UI delle funzionalità già disponibili nelle milestone 01–06, integrando il frontend React/TypeScript con le API e gli eventi reali del backend.

Questa milestone colma il gap frontend accumulato nelle milestone precedenti.

**IMPORTANTE**: non ricostruire né riscrivere le milestone 01–06. Il backend, le API, il database e i relativi contratti esistenti devono essere considerati la base del lavoro. Modificare il backend esclusivamente quando necessario per correggere bug, problemi di integrazione o API insufficienti per supportare correttamente la UX prevista.

La UI deve utilizzare dati e API reali. Non utilizzare mock data o dati statici per simulare funzionalità già implementate nel backend.

### Riferimenti

* `SPEC.md`
* `FRONTEND_SPEC.md`
* `ROADMAP.md`
* architettura e API esistenti
* milestone 01–06 già completate

---

### 1. Frontend Architecture Audit

Prima di implementare nuove schermate, analizzare il frontend esistente e produrre un breve report interno con:

* struttura attuale del progetto React;
* routing;
* gestione autenticazione/sessione;
* API client;
* gestione stato;
* gestione errori;
* componenti già disponibili;
* eventuale design system già presente;
* eventuali duplicazioni;
* eventuali problemi architetturali;
* API backend disponibili;
* API mancanti o insufficienti per la UI.

Non procedere a una riscrittura completa del frontend se non strettamente necessaria.

Preferire evoluzione incrementale dell'architettura esistente.

---

### 2. Application Shell

Implementare una struttura applicativa coerente per Lumio.

Desktop:

* sidebar/navigation principale;
* header;
* area contenuto;
* user/account menu;
* logout;
* stato della sessione.

Mobile:

* navigation adatta a schermi piccoli;
* menu/navigation accessibile;
* layout responsive;
* contenuti utilizzabili senza horizontal scrolling non necessario.

Navigation iniziale:

* Dashboard
* Accounts
* Transactions
* Imports
* Rules
* Settings

Le sezioni non ancora implementate possono essere mostrate come non disponibili oppure non essere ancora esposte nella navigation.

Non creare pagine placeholder prive di funzionalità senza una motivazione.

---

### 3. Authentication UI

Integrare il frontend con l'autenticazione reale del backend.

Implementare:

* login;
* registrazione, se prevista dal backend;
* gestione sessione;
* logout;
* redirect dopo autenticazione;
* route protection;
* gestione sessione scaduta;
* loading state;
* error state;
* validazione dei form.

Non memorizzare credenziali o token in modo non sicuro.

Seguire le decisioni architetturali già presenti nello `SPEC.md`.

---

### 4. Accounts UI

Implementare l'interfaccia per la gestione dei conti finanziari.

Funzionalità:

* lista conti;
* dettaglio conto;
* creazione conto;
* modifica conto;
* eliminazione/disattivazione quando prevista;
* visualizzazione saldo;
* banca/provider;
* valuta;
* tipo di conto;
* stato del conto.

Gestire:

* loading;
* empty state;
* error state;
* conferma per operazioni distruttive;
* feedback dopo operazioni completate.

La UI deve utilizzare le API reali.

---

### 5. Transactions UI

Implementare la principale interfaccia di consultazione delle transazioni.

La tabella/lista deve supportare, quando previsto dalle API:

* data;
* descrizione;
* merchant;
* importo;
* valuta;
* conto;
* categoria;
* transaction type;
* stato/classificazione;
* ricerca;
* filtri;
* ordinamento;
* paginazione.

Implementare filtri almeno per:

* intervallo temporale;
* conto;
* categoria;
* tipo di transazione;
* merchant;
* intervallo di importo.

La UI non deve scaricare migliaia di transazioni per poi filtrare tutto nel browser quando il backend supporta o può supportare filtering/pagination server-side.

Implementare:

* transaction detail;
* modifica categoria;
* modifica dei dati consentiti;
* feedback dopo modifica;
* gestione errori.

Se un requisito UI richiede un'API backend non sufficientemente strutturata, documentare il problema e implementare la modifica backend minima necessaria.

---

### 6. Import UI

Integrare completamente il frontend con l'Import Engine della milestone 04 e con il parser Trade Republic della milestone 05.

User flow:

```text
Import
  ↓
Select file
  ↓
Upload
  ↓
Job created
  ↓
Processing
  ↓
Progress
  ↓
Completed / Failed
  ↓
Review result
  ↓
Transactions
```

Implementare:

* selezione file;
* drag & drop quando appropriato;
* validazione preliminare;
* upload;
* stato del job;
* progress;
* risultato;
* errori;
* eventuale duplicate detection;
* link alle transazioni importate.

Utilizzare gli eventi SSE già previsti dall'Import Engine.

**Non implementare polling continuo per sostituire SSE.**

Gestire correttamente:

* connessione SSE persa;
* riconnessione quando appropriato;
* job già completato;
* job fallito;
* refresh della pagina durante un job;
* file duplicato;
* file non supportato.

L'utente deve sempre poter capire chiaramente a che punto si trova l'elaborazione.

---

### 7. Rules UI

Implementare l'interfaccia completa del Rules Engine della milestone 06.

Funzionalità:

* lista regole;
* creazione regola;
* modifica;
* eliminazione;
* attivazione/disattivazione;
* priorità;
* condizioni;
* operatore;
* valore;
* categoria risultante;
* eventuali altri parametri previsti dal dominio.

Supportare gli operatori disponibili:

* equals;
* contains;
* starts_with;
* ends_with;
* regex;
* merchant_equals.

La UI deve rendere comprensibile la logica della regola senza richiedere conoscenze tecniche.

Esempio concettuale:

```text
Se
  Merchant contiene "LIDL"

Allora
  Categoria = Alimentari
```

Non mostrare all'utente una configurazione basata esclusivamente su strutture tecniche interne o JSON.

---

### 8. Classification Review

Implementare una UI per comprendere e correggere le classificazioni delle transazioni.

L'utente deve poter:

* vedere la categoria assegnata;
* capire quando possibile perché è stata assegnata;
* distinguere classificazione manuale, rule-based o altro metodo disponibile;
* correggere la classificazione;
* visualizzare il risultato della correzione;
* creare una regola dalla correzione quando previsto dal backend.

Lo storico delle classificazioni deve essere consultabile quando previsto dalle API.

---

### 9. Dashboard Base

Creare una dashboard iniziale funzionale, ma **non implementare ancora la dashboard completa della milestone 08**.

La dashboard di questa milestone serve principalmente come home applicativa e punto di navigazione.

Può mostrare:

* patrimonio/liquidità disponibili tramite API esistenti;
* numero di conti;
* numero di transazioni;
* ultime transazioni;
* ultimi import;
* eventuali informazioni utili già disponibili.

Non implementare ancora:

* analytics avanzati;
* grafici complessi;
* portfolio analytics;
* performance storiche;
* dashboard finanziaria completa.

Questi elementi appartengono alle milestone successive.

---

### 10. Design System e UI Components

Creare o consolidare un sistema di componenti condivisi.

Quando appropriato utilizzare componenti riutilizzabili per:

* Button;
* Input;
* Select;
* Checkbox;
* Date picker;
* Modal/Dialog;
* Dropdown;
* Table;
* Pagination;
* Badge;
* Card;
* Tabs;
* Toast/Notification;
* Tooltip;
* Loading state;
* Empty state;
* Error state;
* Confirmation dialog;
* Form field.

Evitare duplicazioni di componenti equivalenti.

La UI deve essere coerente in tutte le sezioni.

---

### 11. Loading / Empty / Error States

Ogni pagina o componente che dipende da dati asincroni deve gestire esplicitamente:

```text
Loading
   ↓
Success
   ├── Data
   └── Empty
   ↓
Error
```

Non utilizzare schermate bianche, errori JavaScript non gestiti o componenti vuoti senza spiegazione.

Gli empty state devono spiegare all'utente cosa può fare successivamente.

Esempio:

```text
Non hai ancora importato transazioni.

[Importa un estratto conto]
```

---

### 12. Responsive Design

Tutte le nuove schermate devono essere utilizzabili almeno su:

* desktop;
* tablet;
* smartphone.

Prestare particolare attenzione a:

* tabelle;
* filtri;
* modali;
* form;
* navigation;
* import workflow.

Non limitarsi a ridimensionare il layout desktop.

Su smartphone utilizzare pattern appropriati, ad esempio card/list view quando una tabella completa non è utilizzabile.

---

### 13. Accessibility

Applicare almeno le pratiche fondamentali:

* semantic HTML;
* keyboard navigation;
* focus states;
* labels correttamente associate;
* aria attributes quando necessari;
* contrasto adeguato;
* messaggi di errore accessibili.

I controlli interattivi devono essere utilizzabili anche senza mouse.

---

### 14. API Integration

Centralizzare l'accesso alle API.

Evitare chiamate HTTP duplicate e logica API sparsa casualmente nei componenti.

Gestire centralmente quando appropriato:

* authentication;
* error handling;
* serialization;
* request cancellation;
* retry;
* pagination;
* API types.

Preferire tipi TypeScript derivati dai contratti API quando l'infrastruttura esistente lo permette.

Il frontend non deve duplicare la business logic del backend.

---

### 15. Backend Changes

Non modificare il backend semplicemente per adattarlo comodamente alla UI.

Se una API è realmente insufficiente:

1. identificare il problema;
2. verificare il contratto esistente;
3. apportare la modifica minima necessaria;
4. aggiornare test e documentazione;
5. verificare backward compatibility quando applicabile.

Non introdurre nuove funzionalità di dominio non previste dalla milestone.

---

### 16. Testing

Implementare test frontend appropriati per le funzionalità principali.

Almeno:

* authentication flow;
* accounts;
* transactions;
* import flow;
* rules;
* classification correction.

Quando appropriato utilizzare:

* unit tests;
* component tests;
* integration tests;
* E2E tests.

Creare almeno un E2E flow rappresentativo:

```text
Login
  ↓
Accounts
  ↓
Transactions
  ↓
Import
  ↓
Processing
  ↓
Transactions aggiornate
```

e, quando possibile, un secondo flow:

```text
Login
  ↓
Rules
  ↓
Create rule
  ↓
Apply/correlate classification
  ↓
Verify result
```

---

## Definition of Done

La milestone 06.5 è completata quando:

### Application

* [ ] application shell funzionante;
* [ ] routing funzionante;
* [ ] authentication UI funzionante;
* [ ] session management funzionante;
* [ ] logout funzionante.

### Accounts

* [ ] lista conti;
* [ ] dettaglio;
* [ ] CRUD;
* [ ] loading/error/empty states.

### Transactions

* [ ] lista transazioni;
* [ ] pagination;
* [ ] ricerca;
* [ ] filtri;
* [ ] ordinamento;
* [ ] dettaglio;
* [ ] modifica categoria/classificazione quando prevista.

### Imports

* [ ] upload;
* [ ] job status;
* [ ] SSE progress;
* [ ] success;
* [ ] failure;
* [ ] duplicate handling.

### Rules

* [ ] lista;
* [ ] creazione;
* [ ] modifica;
* [ ] eliminazione;
* [ ] enable/disable;
* [ ] priorità;
* [ ] condizioni;
* [ ] classificazione.

### UX

* [ ] responsive;
* [ ] loading states;
* [ ] empty states;
* [ ] error states;
* [ ] feedback delle operazioni;
* [ ] accessibility foundation;
* [ ] componenti condivisi.

### Quality

* [ ] nessun mock utilizzato per funzionalità già disponibili;
* [ ] API reali integrate;
* [ ] test frontend verdi;
* [ ] E2E principale funzionante;
* [ ] nessuna regressione backend;
* [ ] nessuna violazione multi-tenant;
* [ ] nessun secret nel frontend;
* [ ] build di produzione funzionante.

### Final Review

Prima di dichiarare completata la milestone, produrre un report con:

* funzionalità implementate;
* API utilizzate;
* eventuali modifiche backend effettuate;
* test eseguiti;
* problemi rimasti;
* debito tecnico;
* funzionalità ancora mancanti;
* verifica responsive;
* verifica accessibility;
* conferma che la UI utilizzi dati reali.

**Non iniziare la milestone 07 finché questa Definition of Done non è soddisfatta.**

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
- storico patrimonio (liquidità+debiti+investimenti) consultabile via snapshot, non ricalcolato da zero ogni volta
- storico "Andamento del valore" di un portfolio/ambito investimenti (revisione post-M09, redesign Investimenti):
  ricostruito on-demand dal libro movimenti + storico prezzi (`compute_historical_series`), non da uno snapshot
  congelato — scelta diversa da quella originale sopra, per riflettere correttamente backdating/correzioni e per
  funzionare anche su ambiti senza una riga di snapshot propria (es. "Asset senza portfolio")

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

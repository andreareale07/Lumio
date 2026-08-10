# MASTER PROMPT — SELF-HOSTED PERSONAL FINANCE & WEALTH MANAGEMENT

## 1. Ruolo dell'agente

Agisci come **Senior Software Architect, Senior Full-Stack Developer, Database Architect, Security Engineer e UX/Product Designer**.

Devi progettare e sviluppare una applicazione web moderna, self-hosted, multi-utente e privacy-first per la gestione delle finanze personali e del patrimonio.

Non limitarti a generare codice funzionante: devi produrre un sistema:

* robusto;
* mantenibile;
* modulare;
* sicuro;
* documentato;
* facilmente installabile;
* adatto al self-hosting;
* responsive e utilizzabile perfettamente da smartphone;
* predisposto per future estensioni;
* con una UX moderna e intuitiva;
* senza dipendere obbligatoriamente da servizi AI cloud.

Prima di implementare una funzionalità importante, valuta sempre l'impatto sull'architettura, sul database, sulla sicurezza e sulla UX.

Non introdurre complessità non necessaria.

Non creare microservizi solo per principio.

Preferisci un **modular monolith** ben strutturato, con worker asincroni e interfacce astratte per i servizi esterni.

---

# 2. Visione del prodotto

L'applicazione è una piattaforma personale di:

* personal finance;
* gestione conti;
* gestione entrate e spese;
* categorizzazione automatica dei movimenti;
* analisi finanziaria;
* gestione patrimonio;
* gestione investimenti e portfolio;
* aggregazione di più conti;
* visualizzazione storica;
* automazione tramite regole;
* classificazione AI opzionale;
* importazione di estratti conto PDF;
* esportazione dati;
* integrazione opzionale con Google Sheets.

Il prodotto NON deve essere concepito come:

> "un convertitore PDF → Excel".

La funzione PDF è solamente uno dei sistemi di acquisizione dati.

Il concetto principale deve essere:

> **Financial Hub / Personal Finance & Wealth Management**

Il percorso principale dei dati è:

```text
Documento / Import
        ↓
Parser
        ↓
Dati finanziari normalizzati
        ↓
Regole
        ↓
AI opzionale
        ↓
Classificazione
        ↓
Conti / Spese / Entrate / Patrimonio / Portfolio
        ↓
Analytics
        ↓
Dashboard
```

Google Sheets è solamente una integrazione/export opzionale e NON deve essere una dipendenza dell'applicazione.

---

# 2.1 Product Identity — Lumio

Il nome del progetto/prodotto è:

# Lumio

**Lumio** è il nome ufficiale del prodotto durante lo sviluppo.

Il nome deve essere utilizzato coerentemente in:

* frontend;
* titolo della web application;
* documentazione;
* README;
* Docker metadata quando appropriato;
* schermate di login;
* pagina iniziale;
* email/notifiche eventualmente implementate;
* configurazioni e branding.

Il nome deve essere facilmente modificabile in futuro tramite configurazione, senza dover modificare il codice applicativo in più punti.

## Brand positioning

Lumio deve comunicare:

* chiarezza;
* controllo;
* consapevolezza finanziaria;
* semplicità;
* tecnologia;
* eleganza;
* privacy;
* autonomia dei propri dati.

Il prodotto deve essere percepito come una moderna piattaforma di **Personal Finance & Wealth Management**, non come un semplice software di contabilità o importazione di estratti conto.

### Brand concept

> **Lumio — See your money clearly.**

Il payoff può essere utilizzato come riferimento concettuale e potrà essere modificato successivamente senza modificare l'architettura dell'applicazione.

## Brand personality

Lumio deve avere una personalità:

* moderna;
* elegante;
* intelligente;
* affidabile;
* semplice;
* non burocratica;
* non eccessivamente "corporate";
* non eccessivamente tecnica.

L'interfaccia deve trasmettere la sensazione che Lumio trasformi dati finanziari complessi e frammentati in una visione semplice e comprensibile.

## Naming constraint

Considerare "Lumio" come working product name.

Non assumere che:

* il dominio sia disponibile;
* il nome sia registrabile come marchio;
* tutti i relativi username/repository siano disponibili.

Queste verifiche saranno effettuate separatamente.

Pertanto, implementare il branding in modo centralizzato e facilmente modificabile.

Ad esempio, evitare di inserire stringhe `"Lumio"` sparse nel codice.

Utilizzare invece una configurazione centralizzata:

```text
APP_NAME=Lumio
APP_TAGLINE=See your money clearly.
```

Il nome visualizzato dall'interfaccia deve derivare da questa configurazione quando tecnicamente appropriato.


# 3. Requisiti fondamentali

L'applicazione deve essere:

* multi-user;
* multi-account;
* multi-bank;
* multi-currency, almeno a livello architetturale;
* self-hosted;
* privacy-first;
* responsive;
* utilizzabile da desktop e smartphone;
* installabile tramite Docker;
* funzionante senza AI;
* funzionante senza Google;
* funzionante senza servizi cloud obbligatori;
* predisposta per AI locale;
* predisposta per AI cloud opzionale;
* predisposta per future funzionalità di investimento.

I dati di un utente NON devono essere visibili ad altri utenti.

L'isolamento dei dati deve essere implementato sia a livello applicativo sia, ove appropriato, a livello PostgreSQL tramite **Row-Level Security (RLS)**.

Questo requisito deve essere considerato critico.

---

# 4. Stack tecnologico

Utilizzare preferibilmente:

### Backend

* Python 3.x
* FastAPI
* Pydantic
* SQLAlchemy 2.x
* Alembic
* PostgreSQL
* Redis
* worker asincroni Python

### API

Utilizzare principalmente:

* REST/HTTP per le operazioni applicative;
* SSE oppure WebSocket per aggiornamenti realtime;
* eventuale gRPC/RPC solamente per futuri servizi interni dove abbia un reale vantaggio.

NON utilizzare RPC come architettura principale solo per evitare polling.

Per il progresso dei job utilizzare preferibilmente:

```text
REST → avvio operazione
SSE/WebSocket → aggiornamento stato
```

### Frontend

Utilizzare un moderno framework web component-based.

Preferenza:

* React
* TypeScript
* Vite oppure framework equivalente appropriato
* UI responsive
* componenti accessibili
* grafici interattivi
* PWA/installabilità mobile quando appropriato

Il frontend deve essere progettato mobile-first, pur offrendo una UX desktop completa.

### Deployment

* Docker
* Docker Compose
* `.env`
* health checks
* database migrations
* backup/documentazione
* configurazione semplice

---

# 5. Filosofia architetturale

Utilizzare un **modular monolith**.

Struttura concettuale:

```text
Frontend
    ↓
FastAPI
    ↓
Application / Domain Services
    ↓
Repositories
    ↓
PostgreSQL

FastAPI
    ↓
Redis / Job Queue
    ↓
Workers
    ├── PDF Parser
    ├── OCR
    ├── Classification
    ├── Analytics jobs
    └── Export jobs
```

Non creare microservizi separati nella prima versione.

Tuttavia, progettare interfacce astratte che permettano in futuro di estrarre:

* AI service;
* PDF service;
* OCR service;
* market data service;

senza dover riscrivere il dominio.

---

# 6. Multi-tenancy

Il sistema deve supportare utenti multipli.

Utilizzare il concetto di:

```text
User
   ↓
Workspace
   ↓
Workspace Members
   ↓
Financial Data
```

Anche se nella V1 ogni utente avrà probabilmente un solo workspace personale, questa struttura deve consentire in futuro:

* workspace familiari;
* conti condivisi;
* utenti multipli;
* ruoli;
* permessi;
* condivisione selettiva.

Esempio:

```text
Mario
  ↓
Workspace "Personale"
  ↓
Trade Republic
BancoPosta
Fineco
```

In futuro:

```text
Famiglia Rossi
├── Mario
├── Laura
└── Conto familiare
```

---

# 7. Isolamento dati

Ogni dato appartenente a un workspace deve essere isolato.

Implementare:

1. autorizzazione applicativa;
2. controllo ownership;
3. PostgreSQL Row-Level Security quando appropriato;
4. test automatici specifici per verificare che un utente non possa accedere ai dati di un altro.

È obbligatorio avere test del tipo:

```text
User A → Transaction A → ALLOWED

User A → Transaction B → DENIED
```

Non affidarsi solamente a:

```python
if transaction.user_id == current_user.id:
```

nel codice applicativo.

Il database deve fornire un ulteriore livello di sicurezza.

---

# 8. Database

Utilizzare PostgreSQL.

Non utilizzare SQLite come database principale della produzione.

SQLite può eventualmente essere utilizzato solamente per test o sviluppo locale se utile.

Il database deve essere gestito tramite:

* SQLAlchemy;
* Alembic;
* migration versionate;
* constraint;
* foreign key;
* index;
* unique constraint;
* check constraint dove appropriato.

Non creare le tabelle semplicemente con:

```python
Base.metadata.create_all()
```

in produzione.

Utilizzare Alembic.

All'avvio dell'applicazione deve essere possibile verificare lo stato delle migration ed eventualmente applicare le migration mancanti secondo una procedura sicura.

---

# 9. Deployment PostgreSQL

Supportare due modalità.

## Modalità standard

L'utente non deve avere conoscenze tecniche.

Docker Compose deve poter avviare:

```text
frontend
backend
worker
postgres
redis
```

con:

```bash
docker compose up -d
```

## Modalità power user

L'utente deve poter utilizzare un PostgreSQL già esistente.

Esempio:

```env
DATABASE_URL=postgresql+asyncpg://finance_app:password@192.168.1.20:5432/finance
```

In questo caso il container PostgreSQL interno non deve essere necessario.

Supportare configurazioni Docker Compose alternative/profili.

Il database esterno deve richiedere solamente un utente PostgreSQL dedicato all'applicazione.

NON utilizzare l'utente PostgreSQL amministrativo `postgres` per l'applicazione.

---

# 10. Redis

Redis deve poter essere:

* incluso automaticamente nell'installazione standard;
* esterno per power user.

Utilizzarlo principalmente per:

* job queue;
* stato dei job;
* eventi;
* eventuale cache;
* coordinamento dei worker.

Non utilizzare Redis come database persistente principale dei dati finanziari.

---

# 11. File storage

I PDF caricati devono essere trattati come file privati dell'utente/workspace.

Non utilizzare nomi file prevedibili pubblicamente.

Prevedere una struttura tipo:

```text
storage/
    workspaces/
        <workspace_uuid>/
            imports/
                <import_uuid>/
                    original.pdf
                    ...
```

Il filesystem non deve essere direttamente esposto pubblicamente.

L'accesso deve passare dal backend con autorizzazione.

Supportare eventualmente in futuro storage S3-compatible.

---

# 12. Modello dati principale

Il modello deve distinguere chiaramente:

* utente;
* workspace;
* conto finanziario;
* importazione;
* transazione;
* categoria;
* regola;
* classificazione;
* asset;
* posizione;
* portfolio;
* snapshot;
* provider AI.

Schema concettuale:

```text
User
 │
 └── Workspace
       │
       ├── Members
       │
       ├── Financial Accounts
       │      │
       │      ├── Imports
       │      │      └── Files
       │      │
       │      └── Transactions
       │
       ├── Categories
       ├── Rules
       ├── AI Providers
       ├── Portfolios
       └── Integrations
```

---

# 13. Users

Tabella concettuale:

```text
users
- id UUID PK
- email UNIQUE
- password_hash
- display_name
- is_active
- created_at
- updated_at
```

Non memorizzare password in chiaro.

Utilizzare un algoritmo moderno di password hashing.

Prevedere eventualmente in futuro:

* password reset;
* email verification;
* 2FA;
* passkey/WebAuthn.

---

# 14. Workspaces

```text
workspaces
- id UUID PK
- name
- owner_user_id
- created_at
- updated_at
```

---

# 15. Workspace Members

```text
workspace_members
- workspace_id
- user_id
- role
- created_at
```

Ruoli iniziali:

```text
owner
member
```

Prevedere possibilità di aggiungere:

```text
viewer
admin
```

in futuro.

---

# 16. Banks

Le banche devono essere entità globali.

```text
banks
- id
- code
- name
- country
- created_at
```

Esempi:

```text
Trade Republic
BancoPosta
Fineco
Revolut
```

Non legare una banca a un singolo utente.

---

# 17. Bank Parsers

Separare la banca dal parser.

```text
bank_parsers
- id
- bank_id
- parser_type
- version
- is_active
```

Esempio:

```text
Trade Republic
    parser v1
    parser v2
```

Questo è importante perché i formati PDF possono cambiare.

Implementare un'interfaccia astratta:

```python
class BankParser(Protocol):
    def detect(...)
    def parse(...)
```

Il sistema deve poter aggiungere nuove banche senza modificare il core finanziario.

---

# 18. Financial Accounts

Un conto finanziario appartiene a un workspace.

```text
financial_accounts
- id UUID
- workspace_id
- bank_id
- name
- account_type
- currency
- account_identifier_masked
- is_active
- created_at
- updated_at
```

Tipi iniziali:

```text
checking
savings
brokerage
cash
credit_card
other
```

Non memorizzare informazioni bancarie non necessarie.

---

# 19. Import

Ogni documento importato genera un job/import.

```text
imports
- id
- workspace_id
- financial_account_id
- status
- filename
- file_hash
- period_start
- period_end
- transactions_found
- transactions_imported
- created_at
- completed_at
- error_message
```

Status:

```text
uploaded
queued
processing
parsing
classifying
ready_for_review
completed
failed
cancelled
```

Il `file_hash` deve essere utilizzato per individuare potenziali duplicati.

---

# 20. Transactions

La transazione è il dato finanziario principale.

```text
transactions
- id
- workspace_id
- financial_account_id
- import_id
- transaction_date
- value_date
- description_raw
- description_normalized
- merchant
- reference
- amount
- currency
- direction
- transaction_type
- balance_after
- category_id
- status
- created_at
- updated_at
```

Conservare sempre il valore originale:

```text
description_raw
```

La normalizzazione non deve distruggere l'informazione originale.

---

# 21. Transaction Types

NON considerare ogni movimento come "spesa".

Supportare almeno:

```text
expense
income
transfer
investment
dividend
interest
fee
tax
refund
adjustment
```

Per investimenti:

```text
buy
sell
deposit
withdrawal
```

Un trasferimento tra due conti dello stesso workspace NON deve essere conteggiato come spesa o reddito.

Prevedere in futuro il riconoscimento automatico di coppie di trasferimenti.

---

# 22. Categories

Supportare categorie gerarchiche.

Esempio:

```text
Casa
├── Affitto
├── Bollette
├── Manutenzione

Alimentari
├── Supermercato
├── Mercato

Tempo libero
├── Ristoranti
├── Cinema
├── Sport

Abbonamenti
├── Streaming
├── Software
```

Schema:

```text
categories
- id
- workspace_id NULLABLE
- parent_id NULLABLE
- name
- code
- is_system
- is_active
- sort_order
```

Le categorie di sistema possono avere `workspace_id = NULL`.

---

# 23. Rules Engine

Il sistema deve permettere regole deterministiche prima dell'AI.

Esempio:

```text
NETFLIX → Abbonamenti / Streaming

LIDL → Alimentari / Supermercato

ENI → Trasporti / Carburante
```

Schema:

```text
rules
- id
- workspace_id
- name
- field
- operator
- value
- category_id
- priority
- is_active
- created_at
```

Operatori iniziali:

```text
equals
contains
starts_with
ends_with
regex
merchant_equals
```

Prevedere in futuro:

```text
amount_range
account
transaction_type
```

Le regole devono essere valutate prima dell'AI.

---

# 24. Classificazione

Separare la classificazione dalla transazione.

```text
classifications
- id
- transaction_id
- method
- provider
- model
- category_id
- subcategory_id
- score
- explanation
- created_at
```

Metodi:

```text
rule
ai
user
manual
system
```

Conservare lo storico.

Esempio:

```text
AI → Shopping
User → Alimentari
```

Questo permette di sapere come e perché una classificazione è stata modificata.

---

# 25. AI Layer

L'AI è **OPZIONALE**.

L'applicazione deve funzionare completamente anche con:

```text
AI disabled
```

Implementare un'interfaccia astratta:

```python
class AIClassifier:
    async def classify_transaction(...)
```

Provider iniziali:

```text
NoAI
Ollama
OpenAI
Anthropic
OpenAI-compatible
Custom HTTP endpoint
```

L'utente deve poter configurare il proprio provider.

Esempio:

```text
AI
├── Disabilitata
├── Ollama
├── OpenAI
├── Anthropic
└── Server personalizzato
```

---

# 26. AI locale

Supportare modelli locali tramite un endpoint standardizzato.

Esempio:

```text
Ollama
Gemma
altri modelli compatibili
```

Non assumere che un particolare modello sarà sempre utilizzato.

Il modello deve essere configurabile.

L'applicazione non deve essere legata a Gemma.

---

# 27. AI Cloud

Supportare provider cloud opzionali.

L'utente deve fornire personalmente le proprie credenziali/API key.

Le API key devono:

* essere cifrate a riposo;
* non apparire nei log;
* non essere restituite dalle API;
* essere mascherate nell'interfaccia.

L'applicazione non deve richiedere una API key cloud per funzionare.

---

# 28. Hybrid AI

Supportare un futuro flusso:

```text
Transaction
    ↓
Rules
    ↓
Known?
 ┌──┴──┐
YES    NO
 │      │
STOP   Local AI
          │
       uncertain?
       ┌──┴──┐
      NO     YES
       │       │
      STOP   Cloud AI
```

Non utilizzare ciecamente il campo `confidence` dichiarato dall'LLM.

Implementare eventualmente un confidence score applicativo basato su:

* regola;
* merchant riconosciuto;
* storico;
* similarità;
* risultato AI;
* coerenza della classificazione.

---

# 29. Learning dalle correzioni

Quando l'utente corregge ripetutamente una classificazione:

```text
LIDL → Alimentari
```

il sistema può proporre:

> "Vuoi creare una regola automatica?"

Opzioni:

```text
Solo questo conto
Tutti i miei conti
Non creare la regola
```

Questo deve migliorare progressivamente l'automazione.

---

# 30. Analytics

L'applicazione deve fornire analytics nativi.

Non dipendere da Google Sheets per i grafici.

Supportare:

### Spese

* totale mensile;
* totale annuale;
* confronto mese precedente;
* confronto anno precedente;
* categorie;
* sottocategorie;
* merchant;
* ricorrenze;
* trend;
* media mensile.

### Entrate

* totale;
* stipendio;
* altre entrate;
* andamento storico.

### Cash Flow

```text
Entrate
- Uscite
= Cash Flow netto
```

Escludere correttamente i trasferimenti interni.

---

# 31. Patrimonio

Supportare:

```text
Net Worth
= Cash
+ Investments
+ Other Assets
- Liabilities
```

Prevedere storico del patrimonio.

Esempio:

```text
Gennaio     €145.000
Febbraio    €149.000
Marzo       €151.500
...
```

Utilizzare snapshot quando necessario per ottenere grafici efficienti.

---

# 32. Investment / Portfolio Domain

Il modello deve essere predisposto per gli investimenti.

Separare:

```text
Financial Account
Asset
Position
Investment Transaction
Portfolio
Portfolio Snapshot
```

Esempio:

```text
Investment Account
      ↓
Positions
      ↓
VWCE
Apple
Bonds
...
```

---

# 33. Assets

Supportare inizialmente concettualmente:

```text
ETF
Stock
Bond
Crypto
Fund
Cash
Other
```

Non è necessario implementare immediatamente tutte le tipologie.

L'architettura deve però essere estendibile.

---

# 34. Positions

Una posizione rappresenta la quantità posseduta.

```text
positions
- id
- workspace_id
- account_id
- asset_id
- quantity
- average_cost
- currency
- created_at
- updated_at
```

---

# 35. Investment Transactions

Separare gli acquisti/vendite dai normali movimenti bancari quando necessario.

Supportare:

```text
buy
sell
dividend
deposit
withdrawal
fee
tax
split
```

---

# 36. Portfolio

Permettere portfolio aggregati.

Esempio:

```text
Portfolio "Investimenti"
├── Trade Republic
├── Fineco
└── Degiro
```

L'utente deve poter visualizzare:

```text
singolo conto
```

oppure:

```text
tutti i conti aggregati
```

---

# 37. Portfolio Analytics

Supportare:

* valore attuale;
* performance;
* profit/loss;
* asset allocation;
* distribuzione per strumento;
* distribuzione per categoria;
* distribuzione per conto;
* storico;
* performance temporale.

Grafici:

* area/line chart;
* allocation donut;
* bar chart;
* performance comparison.

---

# 38. Market Data

La parte di market data deve essere astratta.

Non vincolare il core dell'applicazione a un singolo provider.

Creare un'interfaccia:

```python
MarketDataProvider
```

che in futuro possa collegarsi a:

* API esterne;
* provider self-hosted;
* dati manuali;
* provider gratuiti/commerciali.

Se il market data provider non è configurato, l'applicazione deve continuare a funzionare.

---

# 39. Dashboard

La dashboard deve essere il punto centrale dell'applicazione.

Deve rispondere rapidamente a:

> Come stanno le mie finanze?

Mostrare eventualmente:

```text
Patrimonio totale
Liquidità
Investimenti
Debiti
Entrate mese
Spese mese
Cash flow
Performance portfolio
```

Grafici:

* patrimonio nel tempo;
* spese per categoria;
* entrate vs uscite;
* asset allocation;
* ultimi movimenti.

La dashboard deve essere personalizzabile in futuro.

---

# 40. UX

La UX è un requisito fondamentale.

Non creare una UI da gestionale bancario tradizionale.

Principi:

* minimalismo;
* chiarezza;
* gerarchia visiva;
* pochi click;
* feedback immediato;
* responsive;
* accessibilità;
* dark mode;
* stati vuoti ben progettati;
* loading state;
* error state;
* skeleton loading;
* conferme solo quando realmente necessarie.

Non creare flussi contorti.

---

# 41. Navigazione

Navigazione desktop indicativa:

```text
Panoramica

Conti
  ├── Tutti i conti
  └── Singolo conto

Spese
Entrate
Patrimonio
Investimenti

Importazioni

Impostazioni
```

Su smartphone utilizzare una navigazione ottimizzata per touch.

Non limitarsi a "rimpicciolire" la UI desktop.

---

# 42. Import PDF UX

L'utente deve poter:

```text
Importa documento
       ↓
Seleziona PDF
       ↓
Riconoscimento banca
       ↓
Parsing
       ↓
Classificazione
       ↓
Review
       ↓
Conferma
```

Durante il processo mostrare progressivamente:

```text
✓ Documento caricato
✓ Banca riconosciuta
✓ Movimenti estratti
✓ Regole applicate
✓ AI completata
⚠ 8 movimenti da verificare
```

Utilizzare SSE/WebSocket per il progresso.

NON utilizzare polling continuo se non necessario.

---

# 43. Review dei movimenti

La revisione deve concentrarsi sui casi problematici.

Esempio:

```text
327 movimenti importati

✓ 319 classificati
⚠ 8 da verificare
```

L'utente non deve essere costretto a controllare tutti i 327 movimenti.

Mostrare:

* descrizione;
* importo;
* data;
* conto;
* categoria proposta;
* metodo di classificazione;
* eventuale confidence;
* motivo dell'incertezza.

Permettere modifica rapida.

---

# 44. Dashboard conti

Per ogni conto:

```text
Saldo attuale
Entrate
Uscite
Cash flow
Movimenti
Trend saldo
```

Possibilità di filtrare:

```text
periodo
categoria
tipo movimento
importo
merchant
```

---

# 45. Grafici

I grafici devono essere realmente utili e non decorativi.

Grafici fondamentali:

### Spese mensili

```text
Gen Feb Mar Apr May Jun
 █   █   ██  █   █   █
```

### Categorie

Donut/pie chart dove appropriato.

### Entrate vs uscite

Bar chart.

### Patrimonio

Line/area chart.

### Portfolio

Allocation donut + performance line.

Permettere tooltips e interazione.

---

# 46. Filtri

I filtri devono essere coerenti in tutta l'applicazione.

Possibili filtri:

* periodo;
* conto;
* categoria;
* sottocategoria;
* tipo movimento;
* merchant;
* importo;
* valuta.

Supportare date range:

```text
Questo mese
Mese scorso
Ultimi 3 mesi
Ultimi 6 mesi
Ultimo anno
Anno corrente
Personalizzato
```

---

# 47. Google Sheets

Google Sheets è opzionale.

Deve essere implementato come integrazione separata.

Possibilità:

```text
Collega Google
    ↓
Seleziona spreadsheet
    ↓
Esporta
```

Eventualmente in futuro:

```text
sincronizzazione automatica
```

La disattivazione di Google Sheets non deve influenzare nessun'altra funzionalità.

---

# 48. Export

Supportare almeno:

```text
CSV
```

e successivamente:

```text
XLSX
Google Sheets
JSON
```

Gli export devono rispettare i permessi del workspace.

---

# 49. API

Le API devono essere versionate:

```text
/api/v1/
```

Struttura indicativa:

```text
/api/v1/auth
/api/v1/users
/api/v1/workspaces
/api/v1/accounts
/api/v1/transactions
/api/v1/categories
/api/v1/rules
/api/v1/imports
/api/v1/dashboard
/api/v1/analytics
/api/v1/portfolio
/api/v1/assets
/api/v1/positions
/api/v1/ai
/api/v1/integrations
/api/v1/exports
```

Utilizzare OpenAPI generato automaticamente da FastAPI.

---

# 50. Async Jobs

Operazioni lunghe NON devono essere eseguite direttamente nella richiesta HTTP.

Esempi:

* PDF parsing;
* OCR;
* classificazione AI;
* grandi import;
* export;
* market data update.

Pattern:

```text
POST /imports
       ↓
job_id
       ↓
Redis
       ↓
Worker
```

Il client riceve:

```json
{
  "job_id": "...",
  "status": "queued"
}
```

e poi si iscrive agli eventi:

```text
SSE/WebSocket
```

---

# 51. Job Events

Definire eventi standard:

```text
job.created
job.started
job.progress
job.warning
job.completed
job.failed
job.cancelled
```

Payload indicativo:

```json
{
  "job_id": "...",
  "type": "import",
  "stage": "classification",
  "progress": 74,
  "message": "Classifying transactions"
}
```

---

# 52. Sicurezza

La sicurezza è prioritaria perché l'app tratta dati finanziari.

Implementare:

* password hashing;
* sessioni/token sicuri;
* authorization;
* ownership checks;
* RLS;
* CSRF protection dove necessario;
* rate limiting;
* validazione input;
* protezione upload;
* limiti dimensione PDF;
* controllo MIME/type;
* sanitizzazione;
* nessun secret nei log;
* encrypted secrets;
* secure headers;
* HTTPS in deployment;
* audit log.

Non fidarsi mai dei dati provenienti dal client.

---

# 53. PDF Security

I PDF sono input non affidabili.

Il parser deve essere isolato il più possibile.

Prevedere:

* limite dimensione file;
* timeout;
* gestione errori;
* eventuale sandboxing del parser;
* nessuna esecuzione di contenuti;
* MIME validation;
* file hash.

Non assumere che un file con estensione `.pdf` sia realmente un PDF valido.

---

# 54. Privacy

Principio:

> I dati finanziari appartengono all'utente.

L'applicazione deve funzionare senza inviare dati finanziari a servizi esterni.

Se l'utente abilita AI cloud, deve essere consapevole che i dati necessari alla classificazione possono essere inviati al provider configurato.

L'AI locale deve permettere elaborazione completamente interna.

---

# 55. Logging

Non loggare:

* password;
* API key;
* token;
* IBAN completi;
* dati finanziari completi;
* contenuti PDF;
* credenziali OAuth.

I log devono essere utili per debugging ma minimizzare i dati sensibili.

---

# 56. Testing

Implementare test automatici.

### Unit test

Per:

* parser;
* rules engine;
* classification;
* analytics;
* portfolio calculations.

### Integration test

Per:

* PostgreSQL;
* Redis;
* API;
* workers.

### Security tests

Verificare:

```text
User A cannot access User B data
```

su:

* accounts;
* transactions;
* imports;
* files;
* categories;
* rules;
* AI providers;
* integrations;
* portfolios.

### E2E

Flusso minimo:

```text
register
login
create account
upload PDF
parse
classify
review
confirm
dashboard
```

---

# 57. Data integrity

Prevedere constraint per impedire:

* transazioni senza account;
* account appartenenti a workspace diversi;
* categorie appartenenti a workspace diversi;
* classificazioni di transazioni inesistenti;
* posizioni appartenenti ad account di altro workspace.

Prestare particolare attenzione alle relazioni cross-tenant.

---

# 58. Idempotenza

Le operazioni di import devono essere il più possibile idempotenti.

Se lo stesso PDF viene caricato due volte:

```text
file_hash
```

deve permettere di rilevare il duplicato.

Evitare di creare automaticamente doppie transazioni.

---

# 59. Audit

Registrare azioni importanti:

```text
LOGIN
IMPORT_CREATED
IMPORT_COMPLETED
TRANSACTION_UPDATED
CATEGORY_CHANGED
RULE_CREATED
RULE_UPDATED
AI_PROVIDER_CHANGED
GOOGLE_CONNECTED
EXPORT_CREATED
```

Non inserire dati sensibili inutili nell'audit log.

---

# 60. Backup

Documentare backup e restore PostgreSQL.

L'installazione deve rendere chiaro all'utente:

> "I dati sono self-hosted: devi gestire i backup."

Prevedere eventualmente script:

```text
backup.sh
restore.sh
```

in una fase successiva.

---

# 61. Configurazione

Utilizzare `.env`.

Configurazioni indicative:

```env
APP_ENV=production

DATABASE_URL=...
REDIS_URL=...

SECRET_KEY=...

STORAGE_PATH=...

AI_PROVIDER=none
AI_ENDPOINT=...
AI_MODEL=...

GOOGLE_ENABLED=false
```

Non inserire secret direttamente nel repository.

Fornire:

```text
.env.example
```

senza valori reali.

---

# 62. Docker Compose

Fornire almeno:

```text
docker-compose.yml
docker-compose.external-db.yml
.env.example
```

Modalità semplice:

```text
app
worker
postgres
redis
```

Modalità power user:

```text
app
worker
redis
```

con PostgreSQL esterno.

---

# 63. Health checks

Esporre endpoint:

```text
/health
/ready
```

Distinguere:

```text
application alive
```

da:

```text
application ready
```

Verificare eventualmente:

* PostgreSQL;
* Redis;
* storage;
* worker.

---

# 64. Observability

Prevedere:

* structured logging;
* job status;
* health checks;
* error tracking interno.

Non introdurre sistemi complessi come Kubernetes/Prometheus/Grafana nella V1 a meno che siano realmente necessari.

---

# 65. Performance

Ottimizzare soprattutto:

* query con molti movimenti;
* dashboard;
* aggregazioni;
* portfolio;
* filtri.

Utilizzare:

* index appropriati;
* pagination;
* query aggregate;
* caching dove necessario;
* snapshot per dati storici costosi.

NON caricare migliaia di transazioni nel browser se ne servono solamente 50.

---

# 66. UX delle tabelle

Le tabelle devono supportare:

* sorting;
* filtri;
* pagination;
* ricerca;
* selezione;
* modifica rapida;
* responsive behavior.

Su smartphone non utilizzare semplicemente una tabella desktop compressa.

Utilizzare eventualmente card/list layout.

---

# 67. Accessibilità

Rispettare buone pratiche WCAG.

* keyboard navigation;
* focus states;
* contrasto;
* aria labels;
* semantic HTML;
* screen reader compatibility.

Non usare il colore come unica informazione.

---

# 68. Dark Mode

Supportare:

```text
Light
Dark
System
```

senza creare due UI completamente separate.

---

# 69. Responsive

Breakpoint e componenti devono essere progettati per:

* desktop;
* tablet;
* smartphone.

L'esperienza mobile è una parte primaria del prodotto.

---

# 70. PWA

Prevedere in futuro possibilità di installazione come PWA.

L'app deve essere utilizzabile da:

* browser desktop;
* browser mobile;
* home screen smartphone.

Non sviluppare immediatamente una app nativa separata se la PWA soddisfa i requisiti.

La struttura deve comunque permettere in futuro un'app mobile dedicata che utilizzi le stesse API.

---

# 71. Design System

Creare un design system coerente.

Definire:

* colori;
* typography;
* spacing;
* border radius;
* shadows;
* cards;
* buttons;
* inputs;
* tables;
* modals;
* dropdowns;
* badges;
* charts;
* notifications;
* empty states.

Evitare di creare ogni pagina con componenti graficamente diversi.

L'applicazione deve sembrare un unico prodotto.

---

# 72. Filosofia visiva

L'interfaccia deve essere:

* moderna;
* elegante;
* professionale;
* finanziaria ma non fredda;
* visualmente impattante;
* pulita;
* leggibile.

Evitare:

* eccessivo skeuomorphism;
* gradienti gratuiti;
* dashboard sovraccariche;
* animazioni inutili;
* tabelle infinite;
* menu profondi;
* finestre modali per ogni azione.

Le animazioni devono comunicare stato e migliorare la percezione dell'interazione.

---

# 73. Dashboard intelligente

La dashboard deve mostrare le informazioni più importanti senza richiedere configurazione iniziale.

Esempio:

```text
Patrimonio
€184.520
+8.4%

Liquidità
€24.520

Investimenti
€160.000

Spese
€1.842

Entrate
€3.020

Cash Flow
+€1.178
```

Poi grafici.

Non mostrare informazioni vuote o inutili.

Se l'utente non ha investimenti:

NON mostrare un grafico portfolio vuoto.

Mostrare invece:

> "Non hai ancora aggiunto investimenti."

con CTA appropriata.

---

# 74. Empty States

Ogni sezione deve avere uno stato vuoto utile.

Esempio:

```text
Non hai ancora importato movimenti.

Importa il tuo primo estratto conto
[Importa PDF]
```

Non mostrare semplicemente:

```text
No data
```

---

# 75. Error handling

Gli errori devono essere comprensibili.

Non mostrare:

```text
500 Internal Server Error
```

all'utente normale.

Mostrare:

> "Non è stato possibile analizzare il documento."

e fornire:

> "Il PDF potrebbe non essere supportato oppure potrebbe essere protetto."

Nei log conservare il dettaglio tecnico.

---

# 76. Roadmap

Sviluppare in fasi.

## Fase 0 — Foundation

* repository;
* Docker;
* FastAPI;
* React/TypeScript;
* PostgreSQL;
* Redis;
* Alembic;
* authentication;
* users;
* workspaces;
* RLS;
* CI;
* test framework.

## Fase 1 — Accounts & Transactions

* financial accounts;
* banks;
* transactions;
* categories;
* rules;
* import model;
* CSV import.

## Fase 2 — PDF

* PDF upload;
* parser architecture;
* Trade Republic parser;
* import jobs;
* worker;
* progress via SSE/WebSocket;
* review UI.

## Fase 3 — AI

* AI abstraction;
* Ollama;
* local model;
* OpenAI;
* Anthropic;
* custom endpoint;
* classification history.

## Fase 4 — Analytics

* dashboard;
* expenses;
* income;
* cash flow;
* charts;
* net worth;
* historical snapshots.

## Fase 5 — Investments

* assets;
* positions;
* investment transactions;
* portfolio;
* valuation;
* allocation;
* performance.

## Fase 6 — Integrations

* Google Sheets;
* CSV/XLSX;
* future market data providers.

## Fase 7 — Advanced

* recurring expenses;
* budgets;
* goals;
* automatic rules;
* family workspaces;
* notifications;
* advanced AI.

---

# 77. Regola fondamentale sullo sviluppo

NON implementare tutte le funzionalità contemporaneamente.

Procedere per vertical slices.

Per esempio:

```text
Authentication
   ↓
Account
   ↓
Transaction
   ↓
Import
   ↓
Classification
   ↓
Dashboard
```

Ogni fase deve essere realmente funzionante prima di passare alla successiva.

---

# 78. Definition of Done

Una funzionalità è completata solamente quando:

* codice implementato;
* test presenti;
* migration presente se necessaria;
* API documentata;
* autorizzazione verificata;
* RLS verificata se applicabile;
* UI completata;
* loading state presente;
* error state presente;
* empty state presente;
* responsive;
* documentazione aggiornata.

Non considerare una feature completa solamente perché "il codice funziona".

---

# 79. Git

Utilizzare Git.

Commit atomici.

Messaggi chiari.

Non modificare file non correlati senza motivo.

Non introdurre dipendenze inutili.

Prima di aggiungere una libreria chiedersi:

> È realmente necessaria?

Preferire librerie mature e mantenute.

---

# 80. Documentazione

Il repository deve contenere almeno:

```text
README.md
ARCHITECTURE.md
DEVELOPMENT.md
DEPLOYMENT.md
DATABASE.md
SECURITY.md
API.md
CONTRIBUTING.md
.env.example
```

Il README deve permettere a un utente senza esperienza di avviare l'app.

La documentazione tecnica deve invece essere sufficiente a un power user per personalizzare:

* PostgreSQL;
* Redis;
* storage;
* AI;
* networking;
* reverse proxy.

---

# 81. Compatibilità self-hosted

L'app deve poter essere installata su:

* server Linux;
* homelab;
* Proxmox;
* VM;
* mini PC;
* NAS compatibile Docker.

Non assumere disponibilità di GPU.

L'AI locale deve funzionare anche CPU-only.

La GPU deve essere un'accelerazione opzionale, non un requisito.

---

# 82. AI Hardware

Non assumere che l'utente disponga di GPU moderna.

Modelli piccoli e quantizzati devono essere supportati quando ragionevole.

Un modello come Gemma 3 4B può essere utilizzato come esempio di modello locale, ma NON deve diventare una dipendenza dell'architettura.

L'utente deve poter utilizzare:

```text
CPU
GPU
LLM locale
LLM cloud
nessuna AI
```

senza modificare il core dell'applicazione.

---

# 83. Principio privacy-first

Default:

```text
No cloud
No AI cloud
No Google
No external analytics
```

Tutto deve funzionare localmente.

Quando l'utente abilita un'integrazione esterna, questa deve essere esplicita.

---

# 84. Principio "data ownership"

L'utente deve poter esportare i propri dati.

Non creare lock-in.

Prevedere export completo in formato strutturato.

Idealmente:

```text
JSON
CSV
XLSX
```

Il backup deve poter essere ripristinato.

---

# 85. Principio "provider agnostic"

Non legare il sistema a:

* un singolo LLM;
* una singola banca;
* un singolo market data provider;
* Google Sheets;
* un singolo storage.

Utilizzare interfacce/adapters.

Esempio:

```text
BankParser
AIProvider
MarketDataProvider
StorageProvider
ExportProvider
```

---

# 86. Principio "source of truth"

Il database applicativo è la source of truth.

Non sono source of truth:

* PDF;
* Google Sheets;
* CSV;
* AI;
* frontend.

Il PDF è un documento sorgente.

Google Sheets è un'integrazione.

L'AI è un classificatore.

---

# 87. Principio "raw data preservation"

Non eliminare mai il dato originale solamente perché è stato normalizzato.

Conservare:

```text
raw
normalized
derived
```

Esempio:

```text
description_raw
description_normalized
merchant
category
```

Questo è importante per audit, debugging e future classificazioni.

---

# 88. Principio "human in the loop"

L'utente deve poter correggere sempre:

* categoria;
* merchant;
* tipo transazione;
* conto;
* classificazione.

Le correzioni dell'utente hanno priorità rispetto all'AI.

---

# 89. Principio "automation without loss of control"

L'automazione deve essere progressiva.

Il sistema può suggerire:

> "Ho classificato 46 movimenti automaticamente."

Ma deve permettere:

> "Fammi vedere quelli con bassa affidabilità."

L'utente deve sempre poter controllare e correggere.

---

# 90. Criterio finale di prodotto

Il prodotto deve essere percepito come:

> "Un'applicazione moderna per capire e gestire il mio denaro."

NON come:

> "Un software tecnico per importare PDF."

L'utente deve poter entrare nella dashboard e capire in pochi secondi:

* quanto possiede;
* quanto ha disponibile;
* quanto ha speso;
* quanto ha guadagnato;
* come stanno andando i suoi investimenti;
* come è cambiato il patrimonio;
* dove sta spendendo i soldi.

---

# 91. Regole per l'agente AI durante lo sviluppo

Prima di implementare codice:

1. Analizza la struttura esistente.
2. Identifica le dipendenze.
3. Verifica se la funzionalità esiste già parzialmente.
4. Non duplicare codice.
5. Non introdurre architetture inutilmente complesse.
6. Aggiorna il modello dati quando necessario.
7. Crea migration.
8. Crea test.
9. Implementa backend.
10. Implementa frontend.
11. Verifica responsive behavior.
12. Verifica autorizzazione.
13. Verifica isolamento tenant.
14. Aggiorna documentazione.

Dopo ogni milestone:

```text
Run tests
Run lint
Run type checks
Build frontend
Build Docker images
Verify migrations
Verify API
Verify authorization
```

Se qualcosa fallisce, correggilo prima di procedere.

---

# 92. Regola contro le assunzioni arbitrarie

Quando un requisito importante non è definito:

NON inventare una soluzione complessa.

Segnala:

```text
DECISION REQUIRED
```

e proponi massimo 2-3 alternative con:

* vantaggi;
* svantaggi;
* impatto.

Per dettagli minori, invece, fai una scelta ragionevole e documentala.

---

# 93. Primo obiettivo concreto

Il primo milestone deve produrre una applicazione funzionante con:

```text
Docker Compose
        ↓
PostgreSQL
Redis
FastAPI
Worker
Frontend
        ↓
Register
        ↓
Login
        ↓
Workspace
        ↓
Create Financial Account
        ↓
Import CSV
        ↓
View Transactions
        ↓
Categories
        ↓
Rules
        ↓
Dashboard base
```

Il PDF deve essere implementato dopo che il modello dati e il flusso delle transazioni sono solidi.

---

# 94. Primo parser bancario

Il primo parser di riferimento sarà:

```text
Trade Republic
```

ma il codice deve essere progettato affinché il parser sia un plugin/adaptor e non venga inserito direttamente nel dominio.

Successivamente devono poter essere aggiunti:

```text
BancoPosta
Fineco
Revolut
altri istituti
```

senza riscrivere:

* transactions;
* categories;
* dashboard;
* analytics;
* AI.

---

# 95. Obiettivo architetturale finale

L'architettura desiderata è:

```text
                         ┌─────────────────────┐
                         │       CLIENT        │
                         │                     │
                         │ Desktop / Mobile    │
                         │ Browser / PWA       │
                         └──────────┬──────────┘
                                    │
                              REST + SSE
                                    │
                         ┌──────────▼──────────┐
                         │       FASTAPI       │
                         │                     │
                         │ Auth                │
                         │ Authorization       │
                         │ Accounts             │
                         │ Transactions         │
                         │ Imports              │
                         │ Analytics            │
                         │ Portfolio            │
                         │ Integrations         │
                         └───────┬───────┬──────┘
                                 │       │
                         ┌───────▼───┐   │
                         │ PostgreSQL│   │
                         │    + RLS  │   │
                         └───────────┘   │
                                         ▼
                                      Redis
                                         │
                                         ▼
                                      Workers
                                         │
                     ┌───────────────────┼────────────────────┐
                     │                   │                    │
                     ▼                   ▼                    ▼
                 PDF/OCR             Rules Engine          AI Layer
                                                             │
                                      ┌──────────────────────┼──────────────┐
                                      │                      │              │
                                      ▼                      ▼              ▼
                                   Ollama                 OpenAI       Anthropic
                                      │
                                      ▼
                                Local LLM
```

---

# 96. Regola conclusiva

Costruisci il progetto come un prodotto reale, non come una demo.

Priorità:

1. correttezza dei dati;
2. sicurezza;
3. isolamento utenti;
4. semplicità UX;
5. affidabilità;
6. manutenibilità;
7. performance;
8. automazione;
9. estetica;
10. funzionalità avanzate.

Non sacrificare correttezza e sicurezza per aggiungere rapidamente nuove funzionalità.

Non sacrificare la UX per semplificare il backend.

Non sacrificare la modularità per una demo veloce.

Il risultato finale deve essere una piattaforma self-hosted che un utente non tecnico possa installare facilmente, ma che un power user possa configurare profondamente e integrare nel proprio homelab.

**Inizia analizzando il repository e producendo un piano di implementazione dettagliato. Non iniziare a generare centinaia di file contemporaneamente. Procedi per milestone verificabili.**

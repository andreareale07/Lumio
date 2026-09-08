# Lumio

**See your money clearly.**

Personal finance & wealth management, self-hosted e privacy-first. I tuoi dati
finanziari restano sulla tua macchina: nessun servizio cloud obbligatorio,
nessun aggregatore bancario di terze parti, nessuna telemetria.

[![CI](https://github.com/andreareale07/Lumio/actions/workflows/ci.yml/badge.svg)](https://github.com/andreareale07/Lumio/actions/workflows/ci.yml)

> **Stato del progetto: in sviluppo attivo.** Le milestone da 01 a 11 sono
> completate (vedi [`docs/ROADMAP.md`](docs/ROADMAP.md)); la milestone 12
> (packaging + documentazione estesa) è ancora aperta. L'applicazione è
> funzionante e usabile su dati reali, ma le interfacce e lo schema dati
> possono ancora cambiare tra un aggiornamento e l'altro.

---

## Cosa fa

Lumio prende i dati finanziari da dove escono davvero — estratti conto PDF,
CSV, esportazioni del broker — e li trasforma in una rappresentazione unica e
coerente del tuo patrimonio.

### Conti e movimenti

- Conti correnti, carte, contanti, conti titoli, in valute diverse
- Import di estratti conto **PDF e CSV**, con parsing in job asincroni e
  progresso in tempo reale
- Profili di mapping riutilizzabili per i CSV di qualunque banca; parser
  dedicato per **Trade Republic**
- **Deduplicazione** dei movimenti su reimport dello stesso periodo, con coda
  di revisione per i casi ambigui
- Riconoscimento dei **trasferimenti interni** tra conti dello stesso
  workspace via IBAN e nominativo: non contano né come spesa né come entrata
- Il testo originale della transazione (`description_raw`) non viene mai
  modificato: la normalizzazione è sempre affiancata, mai distruttiva

### Categorizzazione

- Motore a **regole** deterministiche, valutate in ordine di priorità
- Classificazione **AI opzionale** — l'app funziona al 100% senza nessun
  provider configurato
- Le correzioni manuali hanno **sempre** priorità sull'AI e sulle regole
- Rilevazione di **spese ricorrenti** e **anomalie** sui pattern di spesa

### Patrimonio e investimenti

- Portafogli, posizioni, transazioni di investimento
- Prezzi di mercato da provider configurabili (Yahoo, Stooq, endpoint custom,
  inserimento manuale) con refresh schedulato e quotazione live sul dettaglio
  titolo
- **Motore fiscale a lotti**: zainetto fiscale, regime amministrato e
  dichiarativo, compensazione progressiva delle minusvalenze, scomposizione
  tra utile realizzato e non realizzato
- Analisi del rendimento con **Modified Dietz**, media mensile, confronto
  anno su anno
- Storico del patrimonio netto e ripartizione per classe di attività

### Dashboard e analisi

- Andamento patrimonio netto, entrate, uscite, ripartizioni
- Filtri temporali coerenti su tutta l'applicazione
- Interfaccia mobile-first, in **italiano e inglese**

### Integrazioni opzionali

- **Google Sheets** — export dei dati su fogli di tua proprietà (richiede un
  progetto Google Cloud tuo, un client OAuth per istanza)
- Provider AI: Anthropic, OpenAI, Ollama (locale), endpoint custom, oppure
  nessuno

---

## Principi di progetto

Queste non sono aspirazioni, sono vincoli rispettati nel codice:

- **Privacy per costruzione.** Nessun dato lascia la tua installazione se non
  sei tu a configurare esplicitamente un'integrazione.
- **Isolamento multi-tenant a doppio livello.** Ogni accesso ai dati passa
  sia da un controllo applicativo di ownership sia dalla **Row-Level Security
  di PostgreSQL**, con `FORCE ROW LEVEL SECURITY` e un ruolo di runtime
  `NOSUPERUSER NOBYPASSRLS`. Un bug applicativo non basta a far uscire i dati
  da un workspace.
- **AI sempre opzionale.** Nessuna funzione essenziale dipende da un modello.
- **Secret cifrati a riposo**, mai nei log, mai restituiti dalle API,
  mascherati in interfaccia.
- **Niente operazioni lunghe nella request HTTP.** Parsing, OCR,
  classificazione, export e import passano da un worker asincrono con eventi
  di progresso.
- **Solo migration versionate.** Mai `create_all()`, mai SQLite fuori dai
  test.

---

## Stack

| Livello | Tecnologie |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic |
| Datastore | PostgreSQL 16 (minimo 13), Redis 7 |
| Job async | arq (worker Redis), eventi SSE verso il client |
| Frontend | React, TypeScript, Vite, PWA-ready, mobile-first |
| Deploy | Docker Compose (profilo standard + profilo Postgres esterno) |
| API | REST versionata `/api/v1/...`, SSE per progresso job |

Architettura a **modular monolith**: niente microservizi, ma interfacce
astratte (`BankParser`, `AIProvider`, `MarketDataProvider`,
`StorageProvider`, `ExportProvider`) per ciò che in futuro potrebbe
diventare un servizio separato.

---

## Avvio rapido

Requisiti: Docker e Docker Compose v2.

```bash
git clone https://github.com/andreareale07/Lumio.git
cd Lumio
cp .env.example .env
docker compose up -d
```

Poi apri <http://localhost:5173> e registra il primo utente.

Servizi avviati: `app` (backend FastAPI), `worker`, `postgres`, `redis`,
`frontend` (nginx che serve la SPA e proxa `/api/`).

Verifica che il backend risponda:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

`/health` è liveness, `/ready` verifica che Postgres e Redis siano
raggiungibili.

Lo schema del database viene applicato automaticamente all'avvio del servizio
`app` (`alembic upgrade head`).

### Configurazione minima

Prima di usare Lumio su dati reali, in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

- `SECRET_KEY` → il valore generato sopra
- `POSTGRES_SUPERUSER_PASSWORD` e `POSTGRES_APP_PASSWORD` → password vere,
  allineando `DATABASE_URL` alla seconda
- `APP_NAME` / `APP_TAGLINE` (e i gemelli `VITE_*`) se vuoi un branding tuo

`DATABASE_URL` deve usare il ruolo applicativo `lumio_app`, **mai** il
superuser: un ruolo superuser ignora sempre le policy RLS, rendendo
l'isolamento multi-tenant inefficace.

Tutte le variabili sono documentate in [`.env.example`](.env.example).

---

## Modalità PostgreSQL esterno

Se hai già un'istanza PostgreSQL e non vuoi un secondo database:

```bash
cp .env.example .env
# modifica DATABASE_URL in .env per puntare al tuo Postgres
docker compose -f docker-compose.external-db.yml up -d
```

**Attenzione:** i due ruoli richiesti dall'app (`lumio_app` e
`lumio_rls_helper`) non vengono creati dalle migration — su un Postgres
esterno vanno preparati a mano una volta sola. Le istruzioni SQL complete sono
nell'intestazione di
[`docker-compose.external-db.yml`](docker-compose.external-db.yml) e, con la
spiegazione del perché, nella
[guida di deploy](docs/DEPLOY_PROXMOX.md#7-scenario-b--agganciarsi-a-un-postgres-già-esistente).

---

## Deploy in produzione

I file compose principali sono tarati sullo sviluppo locale: pubblicano
Postgres e Redis sull'host e non prevedono HTTPS. Per la produzione ci sono
due override pronti, da sovrapporre ai file base:

```bash
# Postgres nel compose
docker compose -f docker-compose.yml \
               -f docker-compose.prod.yml \
               -f docker-compose.prod.local-db.yml up -d --build

# Postgres esterno
docker compose -f docker-compose.external-db.yml \
               -f docker-compose.prod.yml up -d --build
```

Chiudono le porte dei datastore, legano il frontend a `127.0.0.1` dietro un
reverse proxy e attivano la rotazione dei log. Richiedono Docker Compose ≥ 2.24.

Per l'installazione completa — VM, reverse proxy, certificati, backup,
aggiornamenti, checklist finale — segui
**[`docs/DEPLOY_PROXMOX.md`](docs/DEPLOY_PROXMOX.md)**.

Due punti da non scoprire a posteriori:

- Con `APP_ENV=production` il cookie di refresh viene emesso con flag
  `Secure`: **senza HTTPS il login non funziona.**
- Le porte 5432 e 6379 pubblicate dal compose standard vanno chiuse. Redis non
  ha autenticazione.

---

## Sviluppo locale (senza Docker)

Servono comunque un PostgreSQL e un Redis raggiungibili.

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -r requirements-dev.txt   # .venv/bin/pip su macOS/Linux
ruff check .
pytest
```

I test vanno eseguiti su **PostgreSQL e Redis effimeri** (container
usa-e-getta, come in CI), mai sull'istanza che contiene i tuoi dati: la suite
fa `TRUNCATE` sulle tabelle.

### Frontend

```bash
cd frontend
npm install
npm run lint
npm run test        # vitest
npm run test:e2e    # playwright (la prima volta: npx playwright install)
npm run dev
```

### Migration

```bash
cd backend
alembic revision -m "descrizione"   # nuova migration
alembic upgrade head
alembic downgrade -1
```

Ogni migration che introduce una tabella con dati di workspace deve
attivare `ENABLE` + `FORCE ROW LEVEL SECURITY` e le quattro policy separate
(SELECT/INSERT/UPDATE/DELETE): è il pattern seguito da tutte le migration
esistenti, e la revisione lo verifica.

---

## Struttura del repository

```
backend/          FastAPI, worker, modelli, migration Alembic
  app/api/v1/     endpoint REST
  app/parsers/    parser bancari (BankParser)
  app/ai/         provider AI (AIProvider)
  app/marketdata/ provider prezzi (MarketDataProvider)
  alembic/        migration versionate
frontend/         SPA React + TypeScript
  src/features/   una cartella per dominio funzionale
  src/locales/    traduzioni it / en
db/postgres-init/ creazione dei ruoli applicativi (solo primo avvio)
docs/             specifiche e roadmap
```

---

## Documentazione

| Documento | Contenuto |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | Specifica tecnica completa — fonte di verità |
| [`docs/SPEC_PRODUCT.md`](docs/SPEC_PRODUCT.md) | Visione di prodotto e requisiti funzionali |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Milestone e Definition of Done |
| [`docs/DEPLOY_PROXMOX.md`](docs/DEPLOY_PROXMOX.md) | Deploy self-hosted, backup, HTTPS |
| [`docs/SPEC_TAX_REGIME.md`](docs/SPEC_TAX_REGIME.md) | Motore fiscale a lotti |
| [`docs/SPEC_DEDUP_TRANSACTION.md`](docs/SPEC_DEDUP_TRANSACTION.md) | Deduplicazione dei movimenti |
| [`docs/SPEC_STOCK_PRICE.md`](docs/SPEC_STOCK_PRICE.md) | Market data e quotazioni |
| [`docs/SPEC_FE.md`](docs/SPEC_FE.md) · [`docs/SPEC_FE_REDESIGN.md`](docs/SPEC_FE_REDESIGN.md) | Frontend e redesign |

---

## Avvertenze

Lumio è uno strumento di **registrazione e visualizzazione**. Non fornisce
consulenza finanziaria o d'investimento. I calcoli fiscali implementano regole
di giurisdizione configurabili e servono a orientarsi: non sostituiscono un
professionista, e la responsabilità di quanto dichiari resta tua.

Verifica i dati importati prima di basarci decisioni. I parser lavorano su
formati di documento che le banche cambiano senza preavviso.

---

## Licenza

Questo repository non ha ancora un file di licenza: in assenza di uno, tutti i
diritti sono riservati e nessuno può legalmente usare, modificare o
ridistribuire il codice. Se l'intenzione è renderlo utilizzabile da altri,
aggiungere un `LICENSE` è il passo che serve.

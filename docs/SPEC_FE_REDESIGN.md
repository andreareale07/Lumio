# LUMIO — CONTROLLED FRONTEND REDESIGN

## Navigation, Temporal UX, Internationalization and Implementation Strategy

## 0. ROLE

Agisci contemporaneamente come:

* Senior Product Designer
* Senior UX Designer
* Frontend Architect
* Senior Frontend Developer

Stai lavorando sul frontend di **Lumio**, applicazione web self-hosted per la gestione, analisi e consultazione del patrimonio finanziario personale.

Il redesign deve mantenere intatta la logica finanziaria e le funzionalità esistenti.

L'obiettivo di questa fase è migliorare principalmente:

1. Information Architecture
2. Navigation
3. App Shell
4. Temporal UX della dashboard e delle pagine analitiche
5. Internationalization / i18n
6. Consistenza del frontend
7. Responsive behavior
8. Usabilità generale

Il principio fondamentale è:

> COMPLESSITÀ INTERNA → SEMPLICITÀ PER L'UTENTE

Non limitarti a modificare colori, spacing o border-radius.

Prima comprendi l'architettura esistente.

---

# 1. REGOLA FONDAMENTALE: NON MODIFICARE SUBITO IL CODICE

Prima di implementare qualsiasi modifica:

1. analizza completamente il frontend;
2. individua framework e librerie;
3. analizza routing;
4. analizza App Shell;
5. analizza sidebar;
6. analizza tutte le route;
7. analizza componenti condivisi;
8. analizza gestione dello stato;
9. analizza data fetching;
10. analizza API disponibili;
11. analizza dashboard;
12. analizza filtri temporali esistenti;
13. analizza eventuali sistemi di traduzione già presenti;
14. analizza formatter di date, numeri e valute;
15. individua stringhe hardcoded;
16. individua duplicazioni.

NON introdurre una nuova architettura se quella esistente può essere evoluta in modo pulito.

NON creare una seconda strategia di routing.

NON creare una seconda strategia di data fetching.

NON creare una seconda strategia di state management senza una motivazione concreta.

---

# 2. OUTPUT OBBLIGATORIO PRIMA DEL CODICE

Prima di scrivere codice devi produrre un documento di analisi contenente:

### A. Repository audit

* framework
* build system
* routing
* UI library
* CSS/Tailwind
* component architecture
* state management
* data fetching
* API layer
* design tokens
* typography
* responsive strategy
* testing
* lint/typecheck

### B. Route inventory

Elenca tutte le route attualmente presenti.

Per ciascuna:

| Route | Funzione | Entry point | Navigation attuale | Proposta |
| ----- | -------- | ----------- | ------------------ | -------- |

### C. Navigation audit

Identifica:

* voci duplicate;
* voci troppo numerose;
* funzioni di configurazione mescolate alla navigazione principale;
* nomenclatura incoerente;
* gerarchie mancanti;
* route che dovrebbero appartenere a Settings;
* route che potrebbero essere raggruppate.

### D. Temporal UX audit

Individua tutte le pagine che utilizzano:

* date;
* periodi;
* range;
* filtri temporali;
* confronto con periodo precedente;
* YTD;
* mese;
* anno;
* storico.

Documenta dove la UX è incoerente.

### E. i18n audit

Verifica:

* eventuale libreria i18n già installata;
* stringhe hardcoded;
* enum mostrati direttamente all'utente;
* label nelle componenti;
* messaggi di errore;
* toast;
* empty states;
* tooltip;
* date formatting;
* currency formatting;
* number formatting;
* pluralizzazione.

### F. Implementation plan

Proponi una roadmap divisa in fasi.

NON iniziare l'implementazione finché questo audit non è completo.

---

# 3. NUOVA INFORMATION ARCHITECTURE

L'attuale menu è:

| #  | Label               | Route                         |
| -- | ------------------- | ----------------------------- |
| 1  | Panoramica          | `/`                           |
| 2  | Conti               | `/accounts`                   |
| 3  | Transazioni         | `/transactions`               |
| 4  | Spese               | `/expenses`                   |
| 5  | Entrate             | `/income`                     |
| 6  | Patrimonio          | `/net-worth`                  |
| 7  | Investimenti        | `/investments`                |
| 8  | Import              | `/imports`                    |
| 9  | Attività            | `/activity`                   |
| 10 | Categorie           | `/settings/categories`        |
| 11 | Regole              | `/settings/rules`             |
| 12 | AI                  | `/settings/ai`                |
| 13 | Market Data         | `/settings/market-data`       |
| 14 | Valuta              | `/settings/currency`          |
| 15 | Tipi di transazione | `/settings/transaction-types` |
| 16 | Job di sistema      | `/settings/jobs`              |
| 17 | Integrazioni        | `/settings/integrations`      |

Il problema principale è che la sidebar espone troppe funzioni allo stesso livello.

NON vogliamo una sidebar che rappresenti direttamente tutte le route.

La sidebar deve rappresentare la **information architecture**, non l'elenco tecnico delle pagine.

---

# 4. PROPOSTA DI NAVIGATION

Come base di progettazione considera questa struttura:

```text
PANORAMICA
  Dashboard

FINANZE
  Conti
  Transazioni

ANALISI
  Spese
  Entrate

PATRIMONIO
  Patrimonio
  Investimenti

IMPORT
  Import

ATTIVITÀ
  Attività

IMPOSTAZIONI
  Configurazione
```

La struttura finale deve essere verificata contro il repository.

NON assumere che questa proposta sia obbligatoriamente quella definitiva.

Valuta se alcune sezioni devono essere accorpate ulteriormente.

L'obiettivo è ridurre il numero di decisioni che l'utente deve prendere.

---

# 5. SIDEBAR

La sidebar deve essere progettata come una navigazione gerarchica.

Esempio concettuale:

```text
┌─────────────────────────┐
│ LUMIO                   │
│                         │
│  Panoramica             │
│                         │
│  Finanze                │
│    Conti                │
│    Transazioni          │
│                         │
│  Analisi                │
│    Spese                │
│    Entrate              │
│                         │
│  Patrimonio             │
│    Patrimonio           │
│    Investimenti         │
│                         │
│  Import                 │
│  Attività               │
│                         │
│  ─────────────────────  │
│  Impostazioni           │
│                         │
│  Profilo / Workspace    │
└─────────────────────────┘
```

Non necessariamente implementare esattamente questo layout.

Prima analizza l'App Shell esistente.

---

# 6. SETTINGS DEVE DIVENTARE UNA VERA AREA

Questo è un requisito importante.

Le seguenti funzionalità NON devono più apparire come elementi indipendenti nella sidebar principale:

* Categorie
* Regole
* AI
* Market Data
* Valuta
* Tipi di transazione
* Job di sistema
* Integrazioni

Devono essere raggiungibili attraverso:

```text
Impostazioni
```

La route `/settings` deve diventare un **Settings Hub**.

Esempio:

```text
Impostazioni

┌────────────────────────────────────┐
│ Impostazioni                        │
│ Configura il comportamento di      │
│ Lumio.                              │
│                                    │
│ Finanze                            │
│  Categorie                         │
│  Tipi di transazione               │
│  Valuta                            │
│                                    │
│ Automazione                        │
│  Regole                            │
│  AI                                │
│                                    │
│ Dati e integrazioni                │
│  Market Data                       │
│  Integrazioni                      │
│                                    │
│ Sistema                            │
│  Job di sistema                    │
└────────────────────────────────────┘
```

La classificazione esatta deve essere validata dopo l'analisi del repository.

---

# 7. SETTINGS NAVIGATION

La navigazione interna alle impostazioni deve essere moderna e semplice.

Non creare una sidebar secondaria permanente se non è realmente necessaria.

Preferire un modello del tipo:

```text
Impostazioni
      ↓
[ Categoria ]
      ↓
Pagina dettaglio
```

Quando l'utente entra in una sezione:

```text
← Impostazioni

Categorie

...
```

La freccia deve riportare al Settings Hub.

Non usare necessariamente una breadcrumb complessa.

Su pagine più profonde:

```text
← Impostazioni

Regole
```

oppure:

```text
← Regole

Nuova regola
```

La navigazione deve essere prevedibile.

---

# 8. SETTINGS ROUTING

NON eliminare le route esistenti se non necessario.

Preferibilmente preservare:

```text
/settings
/settings/categories
/settings/rules
/settings/ai
/settings/market-data
/settings/currency
/settings/transaction-types
/settings/jobs
/settings/integrations
```

e modificare soprattutto il modo in cui vengono raggiunte.

Se il router supporta nested layouts/routes, valutare:

```text
/settings
  /categories
  /rules
  /ai
  /market-data
  /currency
  /transaction-types
  /jobs
  /integrations
```

Utilizzare il pattern più coerente con il router già presente.

NON fare una migrazione di routing solo per motivi estetici.

---

# 9. SETTINGS UX

Ogni pagina Settings deve avere:

* titolo;
* descrizione breve;
* back navigation;
* contenuto principale;
* stato di caricamento;
* empty state;
* error state;
* feedback dopo salvataggio;
* comportamento responsive.

Esempio:

```text
← Impostazioni

Categorie
Gestisci le categorie utilizzate per classificare le transazioni.

[ contenuto ]

                    [Annulla] [Salva]
```

Evita pagine Settings sovraccariche.

Evita modali quando una pagina dedicata è più chiara.

---

# 9A. FUTURE ROLE-BASED ACCESS CONTROL

La nuova Information Architecture deve essere progettata tenendo conto che in futuro Lumio introdurrà ruoli utente.

I ruoli iniziali previsti saranno indicativamente:

```text
USER
ADMIN
```

Il sistema RBAC completo NON deve essere implementato in questa fase, salvo che il repository disponga già di una struttura per ruoli/permessi che possa essere riutilizzata senza introdurre complessità.

Tuttavia, la nuova navigation e la struttura delle Settings devono essere progettate in modo da supportare naturalmente questa evoluzione.

---

# 9A.1 PRINCIPIO FONDAMENTALE

Separare concettualmente:

```text
NAVIGATION
    ↓
VISIBILITY
    ↓
AUTHORIZATION
```

La navigation determina cosa mostrare all'utente.

La visibility determina quali elementi sono pertinenti al ruolo.

L'authorization determina cosa l'utente è effettivamente autorizzato a fare.

La UI NON deve essere considerata un meccanismo di sicurezza.

Nascondere una voce nella sidebar NON equivale a impedire l'accesso alla relativa funzionalità.

L'autorizzazione reale dovrà essere verificata dal backend/API quando il sistema RBAC verrà implementato.

---

# 9A.2 SETTINGS E RUOLI

La struttura Settings deve permettere in futuro di classificare le singole sezioni in base al ruolo.

Esempio concettuale:

```text
SETTINGS

User-accessible
├── Categorie
├── Regole
├── AI
└── Preferenze

Admin-accessible
├── Market Data
├── Valuta
├── Tipi di transazione
├── Job di sistema
├── Integrazioni
└── Gestione utenti
```

Questa è una classificazione concettuale.

NON assumere automaticamente che queste siano le autorizzazioni definitive.

L'audit del repository dovrà verificare il significato reale delle singole funzionalità.

---

# 9A.3 NAVIGATION MODEL

La navigation NON deve contenere direttamente logica specifica per singolo ruolo sparsa nei componenti.

Evitare pattern come:

```tsx
if (user.role === "ADMIN") {
   ...
}
```

ripetuti in molteplici componenti.

Preferire un modello centralizzato e dichiarativo.

Esempio concettuale:

```text
navigation configuration

section
  label
  icon
  route
  requiredRole / permission
  children
```

Per esempio:

```text
Settings
  Categories
  Rules
  AI
  Market Data → ADMIN
  Currency → ADMIN
  Transaction Types → ADMIN
  Jobs → ADMIN
  Integrations → ADMIN
```

La struttura concreta deve essere adattata all'architettura esistente.

NON implementare una complessa permission engine se oggi non è necessaria.

L'obiettivo è semplicemente evitare una navigation architecture che renda difficile introdurre RBAC successivamente.

---

# 9A.4 ROLE-AWARE SETTINGS HUB

Il Settings Hub deve essere costruito in modo che in futuro possa filtrare le sezioni disponibili in base al ruolo.

Esempio:

```text
ADMIN

Impostazioni

Finanze
  Categorie
  Tipi di transazione
  Valuta

Automazione
  Regole
  AI

Dati e integrazioni
  Market Data
  Integrazioni

Sistema
  Job di sistema

Amministrazione
  Utenti
```

Mentre un normale:

```text
USER

Impostazioni

Finanze
  Categorie

Automazione
  Regole
  AI

Preferenze
  ...
```

deve vedere solamente le sezioni autorizzate.

NON mostrare sezioni vuote.

NON mostrare una categoria Settings se tutte le sue pagine sono nascoste per il ruolo corrente.

---

# 9A.5 FUTURE ADMIN AREA

Prevedere che in futuro possa essere introdotta una sezione:

```text
Amministrazione
```

o:

```text
Admin
```

senza dover riprogettare la sidebar.

Possibili funzionalità future:

```text
Amministrazione
├── Utenti
├── Ruoli
├── Workspace
├── Audit Log
├── Job di sistema
└── Configurazione globale
```

NON implementare queste pagine adesso.

L'architettura deve semplicemente permettere di aggiungerle senza trasformare nuovamente la sidebar.

---

# 9A.6 ROUTE PROTECTION

Quando RBAC verrà implementato, la protezione dovrà esistere anche a livello di routing.

Esempio concettuale:

```text
/settings/jobs
        ↓
requireRole(ADMIN)
        ↓
allowed → render page
denied  → unauthorized / forbidden
```

NON assumere che:

```text
"la voce non appare nel menu"
```

sia sufficiente.

Un utente che accede direttamente a:

```text
/settings/jobs
```

deve comunque essere soggetto ai controlli di autorizzazione.

---

# 9A.7 BACKEND AUTHORIZATION

Il frontend non deve diventare il punto di enforcement dei permessi.

Quando verrà implementato RBAC:

```text
Frontend
    ↓
navigation visibility
    ↓
route protection
    ↓
API
    ↓
backend authorization
```

Il backend/API deve rimanere l'autorità finale.

Il frontend deve gestire correttamente almeno:

```text
403 Forbidden
```

mostrando una UX appropriata.

---

# 9A.8 NON IMPLEMENTARE RBAC PREMATURAMENTE

In questa fase:

NON:

* creare un sistema completo di ruoli;
* aggiungere permission matrix complessa;
* introdurre un permission service se non necessario;
* modificare il backend solo per preparare RBAC;
* aggiungere UI amministrative non richieste;
* duplicare controlli di autorizzazione.

FARE invece:

* progettare navigation dichiarativa;
* evitare role-check sparsi;
* mantenere Settings gerarchico;
* mantenere route semanticamente stabili;
* evitare che la sidebar dipenda rigidamente da tutte le route;
* lasciare spazio a future sezioni Admin.

---

# 9A.9 COMPATIBILITÀ FUTURA

La soluzione scelta per la navigation deve permettere di passare da:

```text
Current
```

a:

```text
USER
ADMIN
```

senza dover riscrivere:

* App Shell;
* Sidebar;
* Settings Hub;
* routing;
* componenti di navigation.

Idealmente il futuro cambiamento dovrebbe essere principalmente:

```text
role/permission data
        ↓
navigation filtering
        ↓
route/API authorization
```

e non una riscrittura dell'interfaccia.

---

# 9A.10 DESIGN PRINCIPLE

Quando progetti la navigation chiediti sempre:

> "Se domani alcune di queste funzionalità diventassero ADMIN-only, posso nasconderle o mostrarle senza cambiare l'architettura?"

Se la risposta è no, la soluzione deve essere rivista.

La navigation deve essere:

```text
GERARCHICA
DICHIARATIVA
ESTENSIBILE
ROLE-AWARE
```

ma NON deve essere inutilmente complessa in assenza di RBAC.

---

# 9A.11 FUTURE ROLE MATRIX

Durante l'audit crea anche una matrice preliminare, senza implementarla:

| Area              | USER | ADMIN | Note                 |
| ----------------- | ---: | ----: | -------------------- |
| Dashboard         |    ✓ |     ✓ |                      |
| Accounts          |    ✓ |     ✓ |                      |
| Transactions      |    ✓ |     ✓ |                      |
| Expenses          |    ✓ |     ✓ |                      |
| Income            |    ✓ |     ✓ |                      |
| Net Worth         |    ✓ |     ✓ |                      |
| Investments       |    ✓ |     ✓ |                      |
| Imports           |    ✓ |     ✓ |                      |
| Activity          |    ✓ |     ✓ |                      |
| Categories        |    ✓ |     ✓ | Verificare           |
| Rules             |    ✓ |     ✓ | Verificare           |
| AI                |    ✓ |     ✓ | Verificare           |
| Market Data       |    ? |     ✓ | Da definire          |
| Currency          |    ? |     ✓ | Da definire          |
| Transaction Types |    ? |     ✓ | Da definire          |
| System Jobs       |    ✗ |     ✓ | Admin-only probabile |
| Integrations      |    ? |     ✓ | Da definire          |
| User Management   |    ✗ |     ✓ | Futuro               |

I valori `?` NON devono essere inventati.

Devono essere discussi come decisioni di prodotto da prendere prima dell'implementazione RBAC.

La matrice serve esclusivamente a verificare che l'architettura proposta sia compatibile con la futura gestione dei ruoli.


# 10. ACTIVE NAVIGATION

La sidebar deve indicare chiaramente dove si trova l'utente.

Deve essere gestito correttamente:

* active parent;
* active child;
* route dirette;
* nested routes;
* refresh;
* deep linking;
* browser back/forward.

Esempio:

```text
Finanze
  Conti          ← active
  Transazioni
```

Se l'utente è su:

```text
/settings/categories
```

deve risultare attiva:

```text
Impostazioni
```

e non devono essere mostrate Categorie come voce indipendente nella sidebar principale.

---

# 11. MOBILE NAVIGATION

Su mobile NON comprimere semplicemente la sidebar desktop.

Progettare una vera esperienza mobile.

Possibili soluzioni:

* drawer;
* sheet;
* bottom navigation per le sezioni principali;
* menu account/settings separato.

La scelta deve essere basata sull'architettura esistente.

Per Settings mobile:

```text
Impostazioni
  >
Categorie
```

Entrando:

```text
← Impostazioni
Categorie
```

La navigazione deve essere naturale anche tramite gesture/browser back.

---

# 12. TEMPORAL UX — PROBLEMA PRINCIPALE

La dashboard e le pagine analitiche devono gestire meglio la dimensione temporale.

Non vogliamo avere filtri temporali differenti e incoerenti tra:

* Dashboard
* Spese
* Entrate
* Patrimonio
* Investimenti
* Analytics
* Cash Flow

Serve un **modello temporale condiviso**.

---

# 13. GLOBAL PERIOD MODEL

Definisci un concetto centralizzato:

```text
Period
```

che rappresenti il periodo attualmente analizzato.

Deve supportare, quando i dati lo consentono:

```text
1M
3M
6M
YTD
1Y
ALL
```

e:

```text
Custom
```

con:

```text
Data inizio
Data fine
```

Non implementare periodi che il backend non è in grado di supportare correttamente.

---

# 14. TEMPORAL SELECTOR

Creare un componente riutilizzabile:

```text
PeriodSelector
```

o nome equivalente coerente con il repository.

Esempio:

```text
Periodo

[ 1M ] [ 3M ] [ 6M ] [ YTD ] [ 1Y ] [ ALL ] [ Personalizzato ]
```

Su mobile:

```text
Periodo
[ Ultimi 6 mesi ▾ ]
```

Aprendo:

```text
Ultimo mese
Ultimi 3 mesi
Ultimi 6 mesi
YTD
Ultimo anno
Tutto
Personalizzato
```

La UI deve adattarsi al contesto.

---

# 15. CUSTOM DATE RANGE

Per il periodo personalizzato:

```text
Dal
[ 01/01/2026 ]

Al
[ 31/07/2026 ]

[Applica]
```

Gestire:

* date non valide;
* data inizio > data fine;
* timezone;
* locale;
* date future;
* periodi troppo grandi se non supportati;
* stato loading;
* aggiornamento dei dati.

---

# 16. PERIOD COMPARISON

La UX temporale deve considerare anche il confronto.

Esempio:

```text
Patrimonio

€ 128.420

+4,8%
vs periodo precedente
```

Oppure:

```text
Spese

€ 3.420

-8,2%
vs periodo precedente
```

Il concetto di:

```text
vs periodo precedente
```

deve essere centralizzato.

Non implementare manualmente la logica di confronto in ogni pagina.

Creare una funzione/componente condivisa, ad esempio:

```text
getComparisonPeriod()
calculatePeriodComparison()
PeriodComparison
```

utilizzando naming coerente con il progetto.

---

# 17. TEMPORAL STATE

Valuta dove deve vivere lo stato temporale.

Preferenza:

1. URL quando il periodo deve essere condivisibile/bookmarkabile;
2. stato locale quando riguarda esclusivamente un componente;
3. global state solo quando realmente necessario.

Esempio concettuale:

```text
/dashboard?period=6m
```

oppure:

```text
/dashboard?from=2026-01-01&to=2026-06-30
```

Non introdurre query parameters se il router/progetto ha già una soluzione migliore.

Il comportamento deve essere:

* refresh-safe;
* back/forward-safe;
* deep-link safe;
* condivisibile quando appropriato.

---

# 18. DASHBOARD TEMPORAL CONTEXT

La dashboard deve rendere evidente il periodo analizzato.

Esempio:

```text
Panoramica

Come stanno andando le tue finanze?

Periodo
[ Ultimi 6 mesi ▾ ]

Patrimonio
€ 128.420
+5,4% vs periodo precedente

Liquidità
€ 42.800

Cash Flow
...
```

Il periodo deve essere visivamente riconoscibile ma non dominante.

NON creare un filtro enorme che occupi metà della dashboard.

---

# 19. CONSISTENZA TEMPORALE

Quando possibile, lo stesso periodo deve controllare:

* net worth chart;
* cash flow;
* spending;
* income;
* portfolio performance;
* eventuali analytics collegate.

Se una sezione necessita di un periodo differente, deve essere esplicitamente indicato.

Evitare:

```text
Dashboard → ultimi 6 mesi
Spese → ultimi 30 giorni
Portfolio → 1 anno
```

senza che l'utente capisca perché.

---

# 20. TEMPORAL UX E CHART

I grafici devono mostrare il periodo in modo coerente.

Il formato delle date sull'asse X deve dipendere dal periodo.

Esempio:

```text
1M → giorni/settimane
6M → mesi
1Y → mesi
ALL → anni/mesi
```

Non mostrare 365 label.

Creare formatter centralizzati.

---

# 21. TEMPORAL DATA FORMATTING

Non scrivere formatter temporali duplicati.

Creare un layer condiviso per:

* date;
* date-time;
* month;
* year;
* relative dates;
* chart labels;
* period labels.

Utilizzare le API native `Intl` o la libreria già presente nel progetto.

Se viene introdotta una libreria, farlo solo se realmente necessario.

---

# 22. INTERNATIONALIZATION — OBIETTIVO

Implementare un sistema i18n reale.

NON limitarsi a creare un dizionario manuale di label.

L'infrastruttura deve gestire:

* traduzioni;
* locale;
* fallback;
* pluralizzazione;
* interpolazione;
* date;
* numeri;
* valute;
* percentuali;
* messaggi;
* errori;
* enum;
* chart labels.

---

# 23. SCELTA DELLA LIBRERIA i18n

Prima analizza il framework.

Se il progetto è React SPA, valuta preferibilmente:

```text
i18next
+
react-i18next
```

Se il progetto utilizza Next.js e l'architettura lo giustifica, valuta una soluzione compatibile con Next.js come:

```text
next-intl
```

Se esiste già una libreria i18n, NON sostituirla senza motivazione.

La scelta deve essere documentata.

Criteri:

* compatibilità con stack esistente;
* semplicità;
* type safety;
* lazy loading;
* pluralizzazione;
* interpolazione;
* testing;
* bundle size;
* manutenzione.

---

# 24. TRANSLATION STRUCTURE

Non creare un unico enorme file di traduzioni.

Preferire una struttura organizzata.

Esempio concettuale:

```text
locales/
  it/
    common.json
    navigation.json
    dashboard.json
    transactions.json
    accounts.json
    settings.json
    import.json
    analytics.json
  en/
    common.json
    navigation.json
    dashboard.json
    transactions.json
    accounts.json
    settings.json
    import.json
    analytics.json
```

La struttura finale deve rispettare lo stack.

---

# 25. TRANSLATION KEYS

Le chiavi devono essere stabili e semanticamente significative.

Preferire:

```text
navigation.settings
navigation.transactions
dashboard.netWorth
settings.categories.title
settings.rules.title
transactions.empty.title
```

Evitare:

```text
text1
label23
button4
```

NON utilizzare il testo italiano come translation key.

---

# 26. NO HARDCODED USER-FACING TEXT

Dopo l'introduzione di i18n:

NON devono rimanere hardcoded componenti come:

```tsx
<h1>Impostazioni</h1>
```

Preferire:

```tsx
<h1>{t("settings.title")}</h1>
```

Questo vale anche per:

* button;
* tooltip;
* dialog;
* toast;
* error;
* empty state;
* aria-label;
* placeholder;
* table headers;
* status;
* navigation.

---

# 27. ENUM E STATUS TRANSLATION

NON mostrare direttamente enum tecnici.

Esempio backend:

```text
PENDING
COMPLETED
FAILED
DUPLICATE
```

Non renderizzare:

```text
PENDING
```

ma usare una mappatura i18n:

```text
status.pending
status.completed
status.failed
status.duplicate
```

Questo vale per:

* transaction types;
* account types;
* statuses;
* import statuses;
* AI providers;
* investment types;
* eventuali enum backend.

---

# 28. NUMBER / CURRENCY / DATE LOCALE

Non utilizzare formatter manuali sparsi nel codice.

Centralizzare il comportamento tramite:

```text
Intl.NumberFormat
Intl.DateTimeFormat
Intl.RelativeTimeFormat
```

o equivalenti già presenti.

La valuta deve rispettare:

* locale;
* currency;
* precisione;
* segno;
* separatori.

Esempio:

Italiano:

```text
128.420,42 €
```

Inglese:

```text
€128,420.42
```

La formattazione deve essere coerente in tutta l'applicazione.

---

# 29. LOCALE ARCHITECTURE

Definire:

```text
defaultLocale
supportedLocales
fallbackLocale
```

Esempio:

```text
it
en
```

ma NON assumere che debbano essere necessariamente questi due.

Analizza il progetto.

Il cambio lingua non deve richiedere modifiche al codice.

---

# 30. LANGUAGE SELECTOR

Se l'applicazione deve permettere il cambio lingua, creare una UI semplice.

Esempio:

```text
Lingua
[ Italiano ▾ ]
```

Non inserire il language selector nella sidebar principale.

È preferibile inserirlo:

* Settings;
* User preferences;
* user menu;

in base all'architettura esistente.

---

# 31. TRANSLATION LOADING

Valutare lazy loading delle traduzioni per namespace/feature.

Non caricare inutilmente tutte le traduzioni se l'architettura rende semplice evitarlo.

Gestire:

* loading;
* fallback;
* missing translation;
* errori.

In development, i missing translation devono essere facilmente individuabili.

---

# 32. TEST i18n

Creare controlli per evitare:

* translation key mancanti;
* namespace mancanti;
* placeholder mancanti;
* mismatch tra locale;
* stringhe hardcoded.

Se possibile aggiungere un controllo CI/build.

Il sistema deve impedire che una traduzione mancante arrivi silenziosamente in produzione.

---

# 33. DESIGN SYSTEM

Navigation, temporal UX e Settings devono utilizzare il design system esistente oppure contribuire a consolidarlo.

Prima analizza:

* colors;
* typography;
* spacing;
* radius;
* buttons;
* inputs;
* cards;
* dropdown;
* tabs;
* dialogs;
* icons;
* focus states.

Non creare componenti duplicati.

---

# 34. COMPONENTI CONDIVISI DA VALUTARE

Valuta la creazione o il refactoring di:

```text
AppShell
Sidebar
NavigationSection
NavigationItem
SettingsHub
SettingsList
SettingsPageHeader
BackNavigation
PeriodSelector
DateRangePicker
PeriodComparison
PageHeader
EmptyState
ErrorState
LoadingState
```

Non creare necessariamente tutti questi componenti.

Creare solo quelli realmente utili.

---

# 35. ACCESSIBILITY

Navigation e Settings devono supportare:

* keyboard navigation;
* focus management;
* aria-label;
* semantic HTML;
* screen reader;
* focus trap nei drawer/dialog;
* contrast;
* reduced motion;
* touch target adeguati.

La freccia "indietro" deve avere un accessible name.

Esempio:

```text
← Torna alle impostazioni
```

e non soltanto un'icona senza contesto.

---

# 36. BACK BUTTON E BROWSER HISTORY

La navigazione Settings deve comportarsi correttamente con:

* click sulla freccia;
* browser back;
* browser forward;
* deep link;
* refresh;
* apertura diretta di `/settings/categories`.

Non implementare un sistema di back navigation che rompa la history del browser.

---

# 37. RESPONSIVE SETTINGS

Desktop:

```text
Settings Hub
↓
Settings Detail
```

Mobile:

```text
Impostazioni
   ↓
Categorie
   ↓
← Impostazioni
Categorie
```

Utilizzare progressive disclosure.

Non mostrare simultaneamente tutte le impostazioni su mobile.

---

# 38. PERFORMANCE

Non introdurre complessità inutile.

Prestare attenzione a:

* rendering della sidebar;
* chart rerender;
* period changes;
* translation changes;
* data refetch;
* large transaction lists.

Cambiare lingua non deve causare richieste API inutili.

Cambiare periodo deve aggiornare solo i dati realmente dipendenti dal periodo.

---

# 39. API CONTRACT

NON modificare il backend per comodità frontend.

Prima verifica quali dati sono disponibili.

Per la temporal UX:

* verifica quali endpoint supportano date/range;
* verifica aggregazioni;
* verifica period comparison;
* verifica storico net worth;
* verifica portfolio history.

Se manca un dato:

1. documenta il problema;
2. verifica se può essere calcolato correttamente dal frontend;
3. se non può esserlo, documenta l'API change minimo necessario;
4. NON inventare dati.

---

# 40. IMPLEMENTATION PHASES

Procedere rigorosamente per fasi.

## PHASE 0 — AUDIT

Solo analisi.

Output:

* repository audit;
* route inventory;
* navigation audit;
* temporal audit;
* i18n audit;
* problemi;
* rischi;
* proposta architetturale.

NON modificare il codice.

---

## PHASE 1 — NAVIGATION ARCHITECTURE

Implementare:

* nuova sidebar;
* grouping;
* active states;
* Settings Hub;
* Settings navigation;
* back navigation;
* responsive navigation.

NON modificare ancora tutte le pagine interne.

### Exit criteria

* tutte le route esistenti sono raggiungibili;
* nessuna funzionalità viene persa;
* Settings è raggiungibile dalla nuova navigation;
* nested Settings funzionano;
* browser history funziona;
* mobile navigation funziona.

Eseguire:

```text
lint
typecheck
tests
```

---

## PHASE 2 — TEMPORAL SYSTEM

Implementare:

* Period model;
* PeriodSelector;
* custom date range;
* comparison period;
* formatter;
* URL/state synchronization;
* dashboard integration.

Poi estendere progressivamente alle altre pagine.

### Exit criteria

* periodo coerente;
* nessun formatter duplicato;
* refresh-safe;
* browser back/forward-safe;
* responsive;
* nessuna regressione.

---

## PHASE 3 — i18n FOUNDATION

Implementare:

* libreria i18n scelta;
* locale configuration;
* namespaces;
* translation loader;
* fallback;
* locale formatting;
* translation hooks/utilities.

NON tradurre immediatamente ogni singola schermata.

Prima costruire l'infrastruttura.

### Exit criteria

* almeno una lingua completa;
* seconda lingua di test;
* date/number/currency localizzati;
* missing translations individuabili;
* nessuna regressione.

---

## PHASE 4 — i18n MIGRATION

Migrare progressivamente:

1. App Shell
2. Navigation
3. Settings
4. Dashboard
5. Transactions
6. Accounts
7. Import
8. Analytics
9. Portfolio
10. restante frontend

Rimuovere progressivamente le stringhe hardcoded.

---

## PHASE 5 — DASHBOARD

Dopo che Navigation, Temporal UX e i18n foundation sono stabili, procedere con il redesign approfondito della dashboard.

La dashboard deve rispondere immediatamente:

> Come stanno andando le mie finanze?

Considerare:

* patrimonio;
* liquidità;
* cash flow;
* spese;
* entrate;
* portfolio;
* attività recente;
* elementi che richiedono attenzione.

Non mostrare tutto contemporaneamente.

Utilizzare gerarchia e progressive disclosure.

---

# 41. CONTROLLED DEVELOPMENT RULE

Dopo ogni fase:

1. esegui lint;
2. esegui typecheck;
3. esegui test;
4. verifica route;
5. verifica responsive;
6. verifica console errors;
7. verifica regressioni;
8. verifica visualmente le parti modificate.

NON proseguire automaticamente se una fase introduce errori architetturali significativi.

In caso di problema:

```text
STOP
↓
documenta problema
↓
proponi soluzione
↓
correggi
↓
ripeti verifiche
↓
continua
```

---

# 42. REGRESSION CHECKLIST

Prima di considerare completata una fase verifica almeno:

* login;
* logout;
* dashboard;
* accounts;
* transactions;
* expenses;
* income;
* net worth;
* investments;
* imports;
* activity;
* categories;
* rules;
* AI;
* market data;
* currency;
* transaction types;
* jobs;
* integrations.

Nessuna di queste funzionalità deve essere accidentalmente rimossa.

---

# 43. VISUAL QA

Verificare almeno:

```text
1440px
1280px
1024px
768px
390px
375px
```

Controllare:

* sidebar;
* Settings Hub;
* Settings detail;
* back navigation;
* mobile navigation;
* period selector;
* date picker;
* charts;
* overflow;
* typography;
* buttons;
* focus;
* loading;
* error;
* empty state.

---

# 44. NON FARE

NON:

* riscrivere tutto il frontend in un unico passaggio;
* cambiare backend senza necessità;
* eliminare funzionalità;
* introdurre una nuova libreria senza valutarne l'impatto;
* creare componenti duplicati;
* duplicare la logica dei periodi;
* duplicare formatter;
* duplicare translation logic;
* lasciare stringhe hardcoded dopo la migrazione i18n;
* usare enum backend direttamente nella UI;
* creare una sidebar gigantesca;
* creare una seconda sidebar Settings permanente senza necessità;
* usare modali per ogni configurazione;
* aggiungere grafici solo per estetica;
* usare il colore come unico indicatore di stato.

---

# 45. DECISION PRINCIPLES

Quando hai due soluzioni possibili:

### Preferisci

```text
semplice
```

a:

```text
complesso
```

### Preferisci

```text
gerarchia
```

a:

```text
tutte le informazioni contemporaneamente
```

### Preferisci

```text
componente condiviso
```

a:

```text
duplicazione
```

### Preferisci

```text
progressive disclosure
```

a:

```text
menu sempre aperti
```

### Preferisci

```text
information architecture
```

a:

```text
route tecniche esposte all'utente
```

### Preferisci

```text
consistenza
```

a:

```text
soluzioni locali
```

---

# 46. DEFINITION OF DONE

Questa milestone sarà considerata completata quando:

## Navigation

* la sidebar non espone più tutte le funzioni allo stesso livello;
* le funzionalità sono raggruppate;
* Settings è una sezione autonoma;
* Settings ha un Hub;
* le pagine Settings hanno back navigation;
* nested routes funzionano;
* browser history funziona;
* mobile navigation è coerente.

## Temporal UX

* esiste un modello temporale condiviso;
* il periodo è coerente nella dashboard;
* esistono preset;
* esiste custom range;
* esiste comparison quando supportato;
* i grafici rispettano il periodo;
* formatter temporali sono centralizzati.

## i18n

* esiste una vera infrastruttura i18n;
* le translation keys sono organizzate;
* non esistono stringhe hardcoded nelle aree migrate;
* enum/status sono tradotti;
* date sono localizzate;
* numeri sono localizzati;
* valute sono localizzate;
* pluralizzazione/interpolazione funzionano;
* missing translations sono rilevabili.

## Quality

* lint passa;
* typecheck passa;
* test passano;
* nessuna regressione funzionale significativa;
* responsive verificato;
* accessibility verificata;
* console senza errori introdotti dal redesign.

---

# 47. OUTPUT FINALE DI OGNI FASE

Alla fine di ogni fase produci un breve report:

```text
PHASE:
[Nome]

COMPLETED:
- ...

FILES CHANGED:
- ...

ARCHITECTURAL DECISIONS:
- ...

ROUTES AFFECTED:
- ...

API CHANGES:
- None
oppure
- ...

TESTS:
- lint: PASS/FAIL
- typecheck: PASS/FAIL
- tests: PASS/FAIL

KNOWN ISSUES:
- ...

NEXT PHASE:
- ...
```

Non dichiarare una fase completata se i relativi exit criteria non sono soddisfatti.

---

# 48. PRIORITÀ ASSOLUTA

La priorità di questa attività è:

```text
1. Information Architecture
2. Navigation
3. Temporal UX
4. i18n foundation
5. Design consistency
6. Visual polish
```

Non invertire queste priorità.

Una UI molto bella con una navigation confusa è un fallimento.

Una dashboard esteticamente sofisticata ma con una gestione temporale incoerente è un fallimento.

Un'app apparentemente tradotta ma con stringhe hardcoded, date incoerenti e enum tecnici visibili non è una vera internazionalizzazione.

L'obiettivo è trasformare Lumio in un prodotto che sia:

```text
MODERNO
ELEGANTE
PROFESSIONALE
CHIARO
INTUITIVO
COERENTE
```

ma soprattutto:

```text
FACILE DA CAPIRE
```

# 49. FIRST ACTION

La tua prima azione NON deve essere modificare il codice.

Devi:

1. analizzare il repository;
2. analizzare il frontend;
3. analizzare il routing;
4. analizzare la navigation esistente;
5. analizzare Settings;
6. analizzare dashboard;
7. analizzare la gestione temporale;
8. analizzare l'eventuale i18n;
9. analizzare API e data fetching;
10. produrre l'audit richiesto.

Solo dopo aver prodotto l'analisi puoi proporre e iniziare la PHASE 1.

NON saltare l'audit.

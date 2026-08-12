\# MASTER PROMPT — LUMIO FRONTEND



\## 1. Ruolo dell'agente



Agisci come \*\*Senior Frontend Architect, Senior React/TypeScript Developer, UX Designer, UI Designer e Design System Engineer\*\*.



Devi progettare e sviluppare il frontend completo di \*\*Lumio\*\*, una moderna piattaforma self-hosted per personal finance e wealth management.



Il frontend non deve essere considerato una semplice interfaccia per le API backend.



Deve essere progettato come un prodotto completo, con particolare attenzione a:



\* UX;

\* usabilità;

\* chiarezza;

\* gerarchia delle informazioni;

\* visualizzazione dei dati finanziari;

\* responsive design;

\* mobile UX;

\* accessibilità;

\* performance;

\* consistenza visiva;

\* gestione degli stati;

\* feedback all'utente;

\* sicurezza lato client.



L'obiettivo è creare un'interfaccia che faccia percepire Lumio come un prodotto finanziario moderno, professionale e premium.



\---



\# 2. Product Identity



Il prodotto si chiama:



\# Lumio



Payoff di riferimento:



> \*\*Lumio — See your money clearly.\*\*



Lumio deve comunicare:



\* chiarezza;

\* controllo;

\* consapevolezza;

\* semplicità;

\* tecnologia;

\* affidabilità;

\* privacy;

\* eleganza.



Il frontend deve evitare l'aspetto tipico dei software contabili tradizionali.



NON deve sembrare:



\* un ERP;

\* un gestionale bancario;

\* un foglio Excel;

\* una dashboard amministrativa anni 2000.



Deve sembrare una moderna applicazione fintech/wealth management.



\---



\# 3. Principi UX fondamentali



Seguire questi principi in tutto il frontend.



\## 3.1 Clarity first



Ogni schermata deve rispondere chiaramente a:



> "Cosa sto guardando?"



e:



> "Cosa posso fare adesso?"



\---



\## 3.2 Progressive disclosure



Non mostrare tutte le informazioni contemporaneamente.



Mostrare prima:



\* informazioni principali;

\* azioni principali;

\* stato.



Permettere di approfondire successivamente.



\---



\## 3.3 Minimal cognitive load



Evitare:



\* menu profondi;

\* modali inutili;

\* schermate con troppe informazioni;

\* azioni nascoste;

\* terminologia tecnica.



\---



\## 3.4 Consistency



Lo stesso tipo di azione deve apparire e comportarsi nello stesso modo in tutta l'applicazione.



Esempio:



```text

Primary Action

Secondary Action

Destructive Action

```



devono avere comportamenti e stili coerenti.



\---



\## 3.5 Feedback immediato



Ogni operazione deve produrre feedback.



Esempi:



```text

Saving...

Saved

Processing...

Completed

Error

```



Mai lasciare l'utente senza sapere cosa sta succedendo.



\---



\# 4. Frontend Stack



Utilizzare:



\* React;

\* TypeScript;

\* Vite o framework equivalente;

\* React Router;

\* TanStack Query;

\* React Hook Form;

\* Zod;

\* libreria di grafici moderna;

\* libreria di icone coerente;

\* CSS moderno oppure Tailwind CSS;

\* component architecture modulare.



La scelta delle singole librerie può essere modificata se esiste una motivazione tecnica concreta.



Non introdurre una libreria solamente perché "è popolare".



\---



\# 5. Frontend Architecture



Strutturare il frontend per feature/domain.



Esempio:



```text

src/

├── app/

│   ├── router/

│   ├── providers/

│   └── config/

│

├── components/

│   ├── ui/

│   ├── charts/

│   ├── forms/

│   └── layout/

│

├── features/

│   ├── auth/

│   ├── dashboard/

│   ├── accounts/

│   ├── transactions/

│   ├── expenses/

│   ├── income/

│   ├── net-worth/

│   ├── portfolio/

│   ├── imports/

│   ├── categories/

│   ├── rules/

│   ├── ai/

│   └── integrations/

│

├── hooks/

├── lib/

├── services/

├── types/

└── styles/

```



Non creare una struttura monolitica dove tutti i componenti vivono nella stessa cartella.



\---



\# 6. API Layer



Il frontend deve comunicare con il backend esclusivamente tramite API definite.



Creare un layer centralizzato:



```text

services/

&#x20;   apiClient

```



Non effettuare fetch casuali direttamente dentro i componenti.



Utilizzare TanStack Query o equivalente per:



\* caching;

\* invalidation;

\* refetch;

\* loading;

\* error handling;

\* optimistic updates quando appropriato.



\---



\# 7. Authentication



Creare:



```text

/login

/register

/forgot-password

```



quando supportati dal backend.



Login:



```text

┌───────────────────────────────┐

│                               │

│             Lumio             │

│                               │

│      See your money clearly   │

│                               │

│ Email                         │

│ \[\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_]   │

│                               │

│ Password                      │

│ \[\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_]   │

│                               │

│        \[ Accedi ]             │

│                               │

│ Password dimenticata?         │

│                               │

└───────────────────────────────┘

```



La pagina deve essere:



\* semplice;

\* elegante;

\* responsive;

\* accessibile.



\---



\# 8. Application Shell



Una volta autenticato, utilizzare un'app shell consistente.



Desktop:



```text

┌────────────────────────────────────────────────────────────┐

│ Lumio                                  Search   🔔   Avatar │

├───────────────┬────────────────────────────────────────────┤

│               │                                            │

│ Overview      │                                            │

│ Accounts      │              MAIN CONTENT                  │

│ Transactions  │                                            │

│ Expenses      │                                            │

│ Income        │                                            │

│ Net Worth     │                                            │

│ Investments   │                                            │

│               │                                            │

│ Imports       │                                            │

│               │                                            │

│ Settings      │                                            │

│               │                                            │

└───────────────┴────────────────────────────────────────────┘

```



Sidebar:



\* collapsible;

\* sticky;

\* stato persistente;

\* icone + testo;

\* tooltips quando collassata.



\---



\# 9. Mobile Application Shell



Su smartphone NON comprimere semplicemente la sidebar.



Utilizzare una navigazione mobile dedicata.



Esempio:



```text

┌──────────────────────────┐

│ Lumio              🔔    │

├──────────────────────────┤

│                          │

│       CONTENT            │

│                          │

│                          │

├──────────────────────────┤

│ Home │ Accounts │ + │ ⋯ │

└──────────────────────────┘

```



La navigation deve essere progettata per il touch.



Prevedere eventualmente un floating action button per:



```text

Importa

```



o:



```text

\+ Nuovo

```



\---



\# 10. Responsive Design



Progettare almeno per:



```text

Mobile

Tablet

Desktop

Large Desktop

```



Non basarsi solamente su breakpoint.



Considerare anche:



\* dimensione contenuto;

\* densità;

\* touch target;

\* orientamento;

\* spazio disponibile.



\---



\# 11. Navigation Architecture



La navigazione principale deve essere:



```text

Overview

Accounts

Transactions

Expenses

Income

Net Worth

Investments

Imports

Settings

```



Non creare livelli inutilmente profondi.



Le sezioni possono avere sottopagine.



\---



\# 12. Dashboard / Overview



La dashboard è la schermata più importante.



Deve rispondere immediatamente:



> Come stanno le mie finanze?



\---



\## 12.1 Header



Mostrare:



```text

Buongiorno



Panoramica finanziaria

```



Eventualmente adattare il messaggio all'orario.



\---



\## 12.2 Global Date Filter



La dashboard deve avere un filtro periodo:



```text

Questo mese

Mese scorso

Ultimi 3 mesi

Ultimi 6 mesi

Quest'anno

Ultimi 12 mesi

Personalizzato

```



Quando possibile, il periodo selezionato deve influenzare i widget pertinenti.



\---



\# 13. KPI Cards



Mostrare:



```text

Patrimonio totale

Liquidità

Investimenti

Entrate

Spese

Cash Flow

```



Ogni card deve contenere:



\* valore principale;

\* variazione;

\* periodo di confronto;

\* eventuale mini chart.



Esempio:



```text

Patrimonio



€184.520,32



↑ 8,4%

vs anno precedente

```



\---



\# 14. Net Worth Chart



Grafico principale:



```text

Patrimonio nel tempo

```



Interazioni:



\* hover;

\* tooltip;

\* cambio periodo;

\* zoom dove appropriato;

\* visualizzazione del valore;

\* eventuale confronto.



Non creare grafici 3D.



\---



\# 15. Cash Flow Chart



Mostrare:



```text

Entrate vs Uscite

```



per periodo.



Esempio:



```text

&#x20;      Entrate

&#x20;        █

&#x20;    █   █

&#x20;█   █   █



&#x20;█   █

&#x20;█   █       Uscite

```



Permettere di cambiare:



```text

giorno

settimana

mese

anno

```



quando i dati lo consentono.



\---



\# 16. Expense Breakdown



Widget:



```text

Spese per categoria

```



Utilizzare donut chart o altra visualizzazione appropriata.



Mostrare anche una lista ordinata:



```text

Casa            €540

Alimentari      €420

Trasporti       €210

Ristoranti      €150

Abbonamenti      €95

Altro           €427

```



Click su una categoria → drill-down.



\---



\# 17. Portfolio Widget



Se l'utente possiede investimenti:



```text

Portfolio



€160.000

+12,4%



ETF          68%

Azioni       12%

Obbligazioni  7%

Cash         13%

```



Se non possiede investimenti:



mostrare un empty state.



Non mostrare un grafico vuoto.



\---



\# 18. Recent Transactions



Mostrare gli ultimi movimenti.



Esempio:



```text

Oggi



Amazon                    -42,90 €

Shopping



LIDL                      -82,30 €

Alimentari



Stipendio              +2.300,00 €

Entrate

```



Click → transaction detail.



\---



\# 19. Quick Actions



La dashboard deve avere azioni rapide:



```text

Importa estratto conto

Aggiungi conto

Visualizza movimenti

```



Su mobile:



```text

\+

```



deve aprire un menu di azioni contestuali.



\---



\# 20. Accounts



Pagina:



```text

/ accounts

```



Mostrare tutti i conti.



Card:



```text

Trade Republic

Conto corrente



€24.520,32



+€1.178 questo mese



\[Apri]

```



Possibilità di visualizzazione:



```text

Grid

List

```



quando utile.



\---



\# 21. Account Detail



URL:



```text

/accounts/:accountId

```



Header:



```text

Trade Republic

Conto corrente



€24.520,32

```



Tabs:



```text

Overview

Transactions

Analytics

```



Mostrare:



\* saldo;

\* trend;

\* entrate;

\* uscite;

\* cash flow;

\* ultime transazioni.



\---



\# 22. Transactions



Pagina:



```text

/transactions

```



Deve essere uno dei componenti più potenti dell'app.



Header:



```text

Movimenti



\[Importa PDF] \[+]

```



Search:



```text

🔎 Cerca movimenti...

```



Filters:



```text

Periodo

Conto

Categoria

Tipo

Importo

Merchant

```



\---



\# 23. Transaction Table



Desktop:



```text

Data

Descrizione

Conto

Categoria

Tipo

Importo

```



Esempio:



```text

10 Ago

Amazon

Trade Republic

Shopping

Spesa

\-42,90 €

```



La tabella deve supportare:



\* sorting;

\* pagination;

\* selection;

\* bulk actions;

\* inline edit;

\* filtering.



\---



\# 24. Mobile Transactions



Su mobile non utilizzare una tabella compressa.



Utilizzare card/list:



```text

┌─────────────────────────────┐

│ Amazon                      │

│ Shopping                    │

│ 10 Ago                      │

│                       -42,90│

└─────────────────────────────┘

```



Swipe actions possono essere introdotte solo se migliorano realmente l'esperienza.



\---



\# 25. Transaction Detail



Aprire drawer o pagina dettaglio.



Mostrare:



```text

Amazon



\-42,90 €



10 Agosto 2026



Conto

Trade Republic



Categoria

Shopping



Tipo

Expense



Classificazione

Regola



Descrizione originale

...

```



Azioni:



```text

Modifica

Cambia categoria

Crea regola

```



\---



\# 26. Classification Indicator



Ogni transazione classificata automaticamente deve poter mostrare la provenienza:



```text

● Manuale

● Regola

✦ AI

● Sistema

```



Se AI:



```text

AI classification

92%

```



La UI deve comunicare che si tratta di una classificazione suggerita, non di una verità assoluta.



\---



\# 27. Expenses



Pagina:



```text

/expenses

```



Header:



```text

Spese



€1.842

↓ 6,8% vs mese scorso

```



Sezioni:



```text

Trend

Categorie

Merchant

Ricorrenze

```



\---



\# 28. Expense Trend



Grafico mensile.



Permettere:



```text

1M

3M

6M

1Y

ALL

```



Tooltip con:



\* totale;

\* variazione;

\* categoria.



\---



\# 29. Expense Categories



Visualizzazione:



```text

Casa

Alimentari

Trasporti

Tempo libero

Abbonamenti

Altro

```



Click su una categoria → dettaglio.



\---



\# 30. Category Drill Down



Esempio:



```text

Alimentari



€420



LIDL            €180

Esselunga       €140

Carrefour        €65

Altro            €35

```



Mostrare:



\* trend;

\* merchant;

\* transazioni;

\* confronto temporale.



\---



\# 31. Income



Pagina:



```text

/income

```



Mostrare:



\* entrate;

\* trend;

\* fonti;

\* categorie;

\* ricorrenze;

\* confronto.



Esempio:



```text

Stipendio        €2.300

Freelance          €500

Interessi           €45

Altro              €175

```



\---



\# 32. Cash Flow



Creare una visualizzazione chiara:



```text

Entrate

\- Uscite

────────────

Cash Flow

```



Il trasferimento tra conti dell'utente non deve falsare il risultato.



\---



\# 33. Net Worth



Pagina:



```text

/net-worth

```



Header:



```text

Patrimonio



€184.520,32



+8,4% ultimi 12 mesi

```



Grafico storico.



Breakdown:



```text

Liquidità       €24.520

Investimenti   €160.000

Altri asset      €5.000

Debiti           €5.000

```



\---



\# 34. Net Worth Attribution



Quando possibile mostrare perché il patrimonio è cambiato.



Esempio:



```text

Variazione patrimonio



Entrate              +€2.300

Spese                -€1.842

Investimenti         +€4.100

Altro                  -€500

────────────────────────────

Totale               +€4.058

```



Questo deve essere visualizzato in modo comprensibile.



\---



\# 35. Investments



Pagina:



```text

/investments

```



Sezione principale:



```text

Portfolio



Valore

€160.000



Performance

+12,4%



Profit/Loss

+€17.640

```



Tabs:



```text

Overview

Positions

Performance

Allocation

Accounts

```



\---



\# 36. Portfolio Allocation



Donut chart:



```text

ETF             68%

Stocks          12%

Bonds            7%

Cash            13%

```



Click → filtro.



\---



\# 37. Portfolio Performance



Grafico:



```text

1M

3M

6M

YTD

1Y

ALL

```



Tooltip:



```text

10 Aug

€160.320

+12,4%

```



Se esiste un benchmark in futuro, permettere confronto.



\---



\# 38. Positions



Lista:



```text

Asset

Quantity

Value

Average Cost

P/L

Performance

```



Esempio:



```text

VWCE

120

€72.430

€63.400

+€9.030

+14,2%

```



\---



\# 39. Portfolio Accounts



Permettere:



```text

Tutti i conti



Trade Republic

Fineco

Degiro

```



La selezione deve aggiornare:



\* valore;

\* allocation;

\* performance;

\* positions.



\---



\# 40. Import Center



Pagina:



```text

/imports

```



Mostrare:



```text

Importazioni recenti



Trade Republic

10 Agosto

327 movimenti

Completed



BancoPosta

8 Agosto

124 movimenti

Completed

```



CTA:



```text

\[Importa documento]

```



\---



\# 41. Import Wizard



Questo è uno dei flussi principali.



\## Step 1 — Upload



```text

Importa estratto conto



Trascina il PDF qui



oppure



\[Seleziona file]

```



Mostrare:



\* formati supportati;

\* dimensione massima;

\* privacy note.



\---



\## Step 2 — Detection



```text

Analisi documento...



✓ PDF valido

✓ Documento leggibile

✓ Banca riconosciuta

```



\---



\## Step 3 — Parsing



```text

Estrazione movimenti



327 movimenti trovati



████████████████░░ 82%

```



\---



\## Step 4 — Classification



```text

Classificazione



319 classificati automaticamente

8 richiedono revisione

```



\---



\## Step 5 — Review



Mostrare solamente i casi problematici.



```text

8 movimenti da verificare

```



Per ciascuno:



```text

Merchant

Importo

Categoria proposta

Metodo

Confidence

```



Azioni:



```text

Accetta

Modifica

Ignora

Crea regola

```



\---



\## Step 6 — Confirmation



```text

Import completato



327 movimenti

319 classificati automaticamente

8 confermati manualmente



\[Visualizza movimenti]

```



\---



\# 42. Realtime Progress



Il frontend deve utilizzare SSE o WebSocket per ricevere:



```text

job.created

job.started

job.progress

job.warning

job.completed

job.failed

```



Non implementare polling continuo se il backend supporta realtime events.



Fallback:



se SSE/WebSocket non è disponibile, utilizzare polling con backoff ragionevole.



\---



\# 43. Progress UI



Il progresso deve mostrare:



```text

Preparazione

✓



Estrazione

✓



Classificazione

●



Salvataggio

○

```



e non solamente:



```text

73%

```



L'utente deve capire cosa sta succedendo.



\---



\# 44. AI Settings



Pagina:



```text

/settings/ai

```



Mostrare:



```text

AI Classification



Provider



○ Disabled

○ Ollama

○ OpenAI

○ Anthropic

○ Custom

```



Se Ollama:



```text

Endpoint

\[http://ollama:11434]



Model

\[gemma3:4b]



\[Test connection]

```



Se cloud:



```text

API Key

\[••••••••••••]



\[Test connection]

```



Mai mostrare la API key completa dopo il salvataggio.



\---



\# 45. AI Privacy UI



Se l'utente seleziona cloud AI, mostrare chiaramente:



> Alcuni dati necessari alla classificazione potrebbero essere inviati al provider selezionato.



Non nascondere questo comportamento.



\---



\# 46. Categories UI



Pagina:



```text

/settings/categories

```



Tree:



```text

Casa

&#x20;├── Affitto

&#x20;├── Bollette

&#x20;└── Manutenzione



Alimentari

&#x20;├── Supermercato

&#x20;└── Mercato

```



Supportare:



\* create;

\* edit;

\* delete;

\* reorder;

\* nesting.



Non permettere eliminazioni che rompano dati esistenti.



\---



\# 47. Rules UI



Pagina:



```text

/settings/rules

```



Esempio:



```text

LIDL

→ Alimentari / Supermercato



NETFLIX

→ Abbonamenti / Streaming

```



Mostrare:



\* priorità;

\* numero di movimenti interessati;

\* attiva/disattiva;

\* modifica;

\* elimina.



\---



\# 48. Rule Creation



Quando l'utente corregge una transazione:



```text

Hai classificato LIDL come Alimentari.



Vuoi applicare questa scelta anche

ai prossimi movimenti LIDL?



\[No]

\[Solo questo conto]

\[Tutti i conti]

```



Questo deve essere un flusso semplice.



\---



\# 49. Settings



Struttura:



```text

Account

Security

Workspace

Categories

Rules

AI

Integrations

Appearance

Data \& Export

```



Utilizzare layout settings moderno:



```text

Sidebar settings

&#x20;       +

Content panel

```



Su mobile:



lista → dettaglio.



\---



\# 50. Google Sheets



Pagina:



```text

/settings/integrations

```



Card:



```text

Google Sheets



Esporta i tuoi dati finanziari

in un foglio Google.



\[Connetti]

```



Dopo connessione:



```text

Connected ✓



Spreadsheet

Lumio Finance



\[Export]

\[Disconnect]

```



Google Sheets deve essere chiaramente opzionale.



\---



\# 51. Export UI



Pagina:



```text

/settings/data

```



Possibilità:



```text

Export CSV

Export XLSX

Export JSON

Google Sheets

```



Mostrare eventuale progresso per export grandi.



\---



\# 52. Search



Implementare una ricerca globale eventualmente accessibile tramite:



```text

⌘ K

```



o:



```text

Ctrl + K

```



Ricerca:



\* transazioni;

\* conti;

\* categorie;

\* portfolio;

\* impostazioni.



Su mobile utilizzare una pagina/modal dedicata.



\---



\# 53. Notifications



Sistema di notifiche non invasivo.



Tipi:



```text

Success

Info

Warning

Error

```



Esempi:



```text

✓ Import completato

⚠ 8 movimenti richiedono revisione

✕ Impossibile elaborare il PDF

```



Non utilizzare toast per informazioni che richiedono un'azione complessa.



\---



\# 54. Loading States



Ogni pagina deve avere loading state.



Preferire skeleton UI a spinner generici.



Esempio:



```text

████████████

██████

████████████████

```



Lo skeleton deve rispecchiare la struttura reale del contenuto.



\---



\# 55. Empty States



Ogni sezione deve avere empty state progettato.



Esempio:



```text

Nessun conto



Aggiungi il tuo primo conto

per iniziare a usare Lumio.



\[ Aggiungi conto ]

```



\---



\# 56. Error States



Ogni query/API deve gestire:



```text

loading

success

empty

error

```



Esempio:



```text

Non siamo riusciti a caricare

i tuoi movimenti.



\[Riprova]

```



Non mostrare errori tecnici non necessari.



\---



\# 57. Confirmation Dialogs



Utilizzare dialog solamente per operazioni realmente importanti:



\* delete account;

\* delete category;

\* disconnect integration;

\* delete import;

\* destructive operations.



Non usare dialog per ogni azione.



\---



\# 58. Forms



Tutti i form devono avere:



\* validation;

\* inline errors;

\* disabled state;

\* loading state;

\* success feedback;

\* keyboard navigation.



Utilizzare Zod per validazione condivisa dove appropriato.



\---



\# 59. Accessibility



Target minimo:



WCAG 2.2 AA dove ragionevole.



Implementare:



\* semantic HTML;

\* keyboard navigation;

\* focus management;

\* aria labels;

\* screen reader support;

\* contrasto;

\* reduced motion;

\* touch targets adeguati.



I grafici devono avere un'alternativa testuale o tabellare quando necessario.



\---



\# 60. Internationalization



Il frontend deve essere predisposto per i18n.



Lingue iniziali:



```text

Italian

English

```



Non inserire stringhe direttamente nei componenti quando questo impedirebbe una futura traduzione.



\---



\# 61. Currency Formatting



Utilizzare formattazione locale.



Esempio italiano:



```text

1.842,50 €

```



Non implementare manualmente il formatting.



Utilizzare API internazionali del browser/TypeScript quando appropriate.



\---



\# 62. Date Formatting



Supportare locale.



Esempio italiano:



```text

10 agosto 2026

```



Nei dati tecnici mantenere ISO.



\---



\# 63. Theme



Supportare:



```text

Light

Dark

System

```



Il tema deve essere persistente.



Evitare flash del tema al caricamento.



\---



\# 64. Design Tokens



Centralizzare:



```text

colors

spacing

radius

typography

shadows

breakpoints

transitions

z-index

```



Non hardcodare valori casualmente nei singoli componenti.



\---



\# 65. Typography



Utilizzare una font moderna e altamente leggibile.



Gerarchia:



```text

Display

H1

H2

H3

Body

Small

Caption

Numeric

```



I valori finanziari devono avere una gerarchia visiva forte.



\---



\# 66. Financial Numbers



Numeri importanti:



```text

€184.520,32

```



devono essere facilmente leggibili.



Supportare:



\* positivo;

\* negativo;

\* zero;

\* valore mancante;

\* percentuale;

\* variazione.



Non affidarsi esclusivamente al colore.



Utilizzare anche:



```text

↑

↓

\+

\-

```



o testo equivalente.



\---



\# 67. Charts



I grafici devono:



\* essere responsive;

\* avere tooltip;

\* supportare touch;

\* essere leggibili;

\* avere legenda quando necessaria;

\* non essere decorativi;

\* non utilizzare effetti 3D;

\* non utilizzare animazioni eccessive.



Quando i dati sono insufficienti, mostrare empty state.



\---



\# 68. Chart Interaction



Esempio:



click su:



```text

Alimentari

```



→ applicare filtro:



```text

Transactions

category=groceries

```



Questo deve creare un'esperienza coerente di drill-down.



\---



\# 69. Global Filters



Quando appropriato, mantenere coerenza tra:



```text

period

account

category

```



Non creare 15 sistemi di filtro diversi.



\---



\# 70. Tables



Le tabelle devono essere:



\* leggibili;

\* responsive;

\* virtualizzate quando necessario;

\* paginated;

\* sortable;

\* filterable.



Non renderizzare migliaia di righe contemporaneamente.



\---



\# 71. Mobile Tables



Quando una tabella non è adatta:



trasformarla in:



```text

list

cards

detail drawer

```



Non forzare scrolling orizzontale come unica soluzione.



\---



\# 72. Mobile Gestures



Utilizzare gesture solamente quando intuitive.



Esempi possibili:



\* swipe per azioni secondarie;

\* pull-to-refresh se utile.



Non creare gesture nascoste che rendano l'app difficile da utilizzare.



\---



\# 73. Performance



Utilizzare:



\* route lazy loading;

\* code splitting;

\* query caching;

\* memoization dove realmente necessaria;

\* virtualizzazione;

\* image optimization;

\* bundle analysis.



Non ottimizzare prematuramente.



Misurare prima.



\---



\# 74. Security Frontend



Non considerare il frontend come sistema di sicurezza.



Il backend rimane la source of truth per authorization.



Il frontend deve comunque:



\* non esporre secret;

\* non salvare API key in localStorage;

\* evitare dati finanziari sensibili nei log;

\* gestire sessioni correttamente;

\* proteggere le route;

\* gestire XSS;

\* non fidarsi dei dati client.



\---



\# 75. Route Guards



Route protette:



```text

/dashboard

/accounts

/transactions

/expenses

/income

/net-worth

/investments

/imports

/settings

```



Se non autenticato:



```text

→ /login

```



\---



\# 76. Optimistic UI



Utilizzare optimistic update solamente quando l'operazione è facilmente reversibile.



Esempio:



```text

toggle rule active

```



Non utilizzarlo ciecamente per operazioni finanziarie critiche.



\---



\# 77. Undo



Quando appropriato:



```text

Categoria modificata.



\[Annulla]

```



Questo è preferibile a chiedere conferma per ogni modifica non distruttiva.



\---



\# 78. Onboarding



Primo accesso:



```text

Welcome to Lumio



Organizza e comprendi

le tue finanze.



\[Inizia]

```



Step:



```text

1\. Crea account

2\. Importa dati

3\. Classifica

4\. Esplora

```



Mostrare progress indicator.



Permettere di saltare gli step non obbligatori.



\---



\# 79. First Value



L'utente deve ottenere valore rapidamente.



Target UX:



```text

Login

&#x20;↓

Import PDF

&#x20;↓

Analisi

&#x20;↓

Review

&#x20;↓

Dashboard

```



Il percorso principale deve essere breve.



\---



\# 80. Import Review UX



Questa schermata deve essere progettata per minimizzare il lavoro manuale.



Esempio:



```text

8 movimenti richiedono attenzione



┌────────────────────────────────────────────┐

│ AMAZON       -42,90 €                      │

│ Categoria: Shopping                       │

│                                            │

│ \[Conferma] \[Modifica] \[Crea regola]       │

└────────────────────────────────────────────┘

```



Supportare:



```text

Accept all high confidence

```



quando appropriato.



\---



\# 81. Accessibility of Financial Information



Non usare solamente:



```text

verde = guadagno

rosso = perdita

```



Usare anche:



```text

+€1.200

\-€430

```



I grafici devono essere interpretabili anche con difficoltà nella percezione dei colori.



\---



\# 82. Responsive Dashboard



Desktop:



```text

3-4 colonne

```



Tablet:



```text

2 colonne

```



Mobile:



```text

1 colonna

```



L'ordine dei widget deve essere ottimizzato per mobile.



Su mobile:



1\. patrimonio;

2\. cash flow;

3\. spese;

4\. investimenti;

5\. movimenti.



\---



\# 83. Quick Action Mobile



Su mobile deve essere facile:



```text

\+ Importa

```



senza navigare Settings → Imports.



\---



\# 84. Account Switching



Se in futuro esistono più workspace:



mostrare:



```text

Workspace

Personal

Family

```



Il cambio workspace deve essere chiaramente visibile.



Mai mischiare dati appartenenti a workspace diversi.



\---



\# 85. Security UX



Quando un'operazione richiede autenticazione o conferma:



```text

Conferma identità

```



Non rendere il sistema inutilmente frustrante.



\---



\# 86. Accessibility Keyboard Shortcuts



Supportare eventualmente:



```text

⌘ / Ctrl + K → Search

Esc → Close dialog

```



Documentare le shortcut.



\---



\# 87. Browser Support



Supportare versioni moderne dei principali browser:



\* Chrome/Chromium;

\* Firefox;

\* Safari;

\* Edge;

\* browser mobile moderni.



Non ottimizzare per browser obsoleti salvo requisito esplicito.



\---



\# 88. PWA



Predisporre:



\* manifest;

\* icons;

\* installability;

\* responsive behavior;

\* eventuale offline shell.



Non implementare offline financial mutations nella prima versione salvo requisiti espliciti.



Il caching offline non deve mai creare inconsistenze sui dati finanziari.



\---



\# 89. Frontend Testing



Implementare:



\### Unit



Testare:



\* formatter;

\* utility;

\* financial calculations lato UI;

\* validation.



\### Component



Testare:



\* forms;

\* dialogs;

\* tables;

\* charts wrappers;

\* import steps.



\### Integration



Testare:



```text

login

account

transactions

import

classification

dashboard

```



\### E2E



Scenario principale:



```text

login

→ dashboard

→ import PDF

→ progress

→ review

→ confirm

→ transactions

→ dashboard

```



\---



\# 90. Visual Regression



Quando possibile utilizzare visual regression per:



\* dashboard;

\* transaction table;

\* import wizard;

\* portfolio;

\* mobile navigation.



L'obiettivo è evitare regressioni grafiche durante lo sviluppo.



\---



\# 91. Frontend Error Boundary



Implementare Error Boundary a livello applicativo.



Se una singola sezione fallisce, non deve necessariamente rompere tutta l'app.



Esempio:



```text

Portfolio widget



Non è stato possibile caricare

questo componente.



\[Riprova]

```



La dashboard deve continuare a funzionare.



\---



\# 92. Offline / Network Errors



Se la rete viene persa:



mostrare:



```text

Connessione persa



Alcuni dati potrebbero non essere aggiornati.

```



Quando ritorna:



```text

Connessione ripristinata

```



Non mostrare falsi dati come se fossero aggiornati.



\---



\# 93. Skeleton Architecture



Definire componenti riutilizzabili:



```text

AppShell

Sidebar

MobileNav

Topbar

PageHeader

SectionHeader

MetricCard

ChartCard

DataTable

EmptyState

ErrorState

Skeleton

ConfirmDialog

Drawer

Toast

FilterBar

DateRangePicker

SearchInput

CategoryBadge

TransactionRow

MoneyDisplay

PercentageDisplay

```



Questi componenti devono costituire il design system di Lumio.



\---



\# 94. Financial UI Components



Creare componenti specifici:



```text

MoneyValue

ChangeIndicator

AccountCard

TransactionItem

CategoryBadge

PortfolioAllocation

PerformanceIndicator

BalanceChart

CashFlowChart

NetWorthChart

```



Evitare di duplicare markup finanziario in ogni pagina.



\---



\# 95. Component API Design



I componenti devono essere:



\* composable;

\* typed;

\* accessibili;

\* prevedibili.



Evitare componenti giganteschi con decine di props non correlate.



\---



\# 96. Frontend State Management



Distinguere:



\### Server state



Gestito tramite TanStack Query.



\### UI state



Gestito localmente o con store leggero.



\### Form state



Gestito con React Hook Form.



NON creare un global state enorme contenente tutti i dati finanziari.



\---



\# 97. URL State



Filtri importanti devono poter essere rappresentati nell'URL quando utile.



Esempio:



```text

/transactions?account=trade-republic\&period=2026-08\&category=food

```



Questo permette:



\* bookmark;

\* back/forward;

\* condivisione interna;

\* refresh senza perdere il contesto.



\---



\# 98. Deep Linking



Ogni risorsa importante deve avere URL diretto.



Esempi:



```text

/accounts/abc

/transactions/123

/portfolio

/imports/xyz

```



\---



\# 99. Breadcrumbs



Utilizzare breadcrumb solamente quando aiutano.



Esempio:



```text

Investimenti / Portfolio / VWCE

```



Non utilizzare breadcrumb su pagine semplici.



\---



\# 100. Modal vs Drawer vs Page



Regola generale:



\### Modal



Per:



\* conferme;

\* azioni brevi;

\* piccoli form.



\### Drawer



Per:



\* dettaglio transazione;

\* quick edit;

\* informazioni contestuali.



\### Page



Per:



\* workflow complessi;

\* import;

\* settings;

\* analytics;

\* portfolio.



\---



\# 101. User Feedback



L'interfaccia deve comunicare chiaramente:



```text

What happened?

What is happening?

What can I do?

```



Mai lasciare un'operazione senza stato.



\---



\# 102. Empty Data vs Error



Distinguere:



```text

No data

```



da:



```text

Failed to load data

```



Non mostrare la stessa UI.



\---



\# 103. Data Freshness



Quando i dati potrebbero essere cached:



mostrare eventualmente:



```text

Aggiornato 2 minuti fa

```



Non mostrare tempi se non realmente disponibili.



\---



\# 104. Confirmation of Financial Actions



Azioni che modificano dati finanziari devono essere chiare.



Esempio:



```text

Salva modifica



Categoria:

Alimentari



Questa modifica sarà applicata

a questa transazione.



\[Annulla] \[Salva]

```



Per azioni massicce:



```text

Applica a 47 movimenti

```



mostrare sempre il numero coinvolto.



\---



\# 105. Bulk Actions



Supportare selezione multipla nella lista movimenti.



Esempio:



```text

47 selezionati



\[Categorizza]

\[Escludi]

\[Modifica tipo]

\[Elimina]

```



Le azioni distruttive devono essere chiaramente distinguibili.



\---



\# 106. Filtering UX



I filtri devono essere:



\* facili da applicare;

\* facili da rimuovere;

\* visibili;

\* persistenti durante la navigazione quando appropriato.



Mostrare chip:



```text

Conto: Trade Republic ×

Categoria: Alimentari ×

Periodo: Agosto ×

```



\---



\# 107. Search UX



La ricerca deve fornire risultati rapidi.



Supportare:



\* merchant;

\* descrizione;

\* riferimento;

\* categoria.



Debounce della ricerca.



\---



\# 108. Pagination



Preferire pagination server-side per grandi dataset.



Non scaricare 100.000 movimenti al browser.



\---



\# 109. Accessibility of Tables



Supportare:



\* headers semantici;

\* keyboard navigation;

\* focus;

\* screen readers.



\---



\# 110. Visual Hierarchy



In ogni schermata:



```text

Primary information

&#x20;      ↓

Secondary information

&#x20;      ↓

Actions

&#x20;      ↓

Details

```



Non dare lo stesso peso visivo a tutto.



\---



\# 111. Color System



Definire semantic colors:



```text

positive

negative

warning

info

neutral

accent

```



Non associare rigidamente colori a significati senza supporto testuale.



\---



\# 112. Motion



Animazioni:



\* brevi;

\* funzionali;

\* non invasive.



Supportare:



```text

prefers-reduced-motion

```



\---



\# 113. Notifications Center



Prevedere in futuro una pagina/pannello:



```text

Notifications

```



con:



\* import completati;

\* errori;

\* classificazioni da rivedere;

\* integrazioni scadute.



\---



\# 114. User Profile



Pagina:



```text

/settings/profile

```



Permettere:



\* nome;

\* email;

\* preferenze;

\* lingua;

\* valuta preferita;

\* tema.



\---



\# 115. Workspace Settings



Pagina:



```text

/settings/workspace

```



Mostrare:



\* workspace name;

\* members;

\* role;

\* future sharing features.



\---



\# 116. Destructive UX



Eliminazione dati finanziari deve essere trattata con cautela.



Esempio:



```text

Eliminare questo import?



Questo rimuoverà 327 movimenti

associati all'importazione.



Questa operazione non può essere annullata.



\[Annulla]

\[Elimina import]

```



Non usare "Delete" senza contesto.



\---



\# 117. Frontend Documentation



Documentare:



```text

FRONTEND.md

DESIGN\_SYSTEM.md

UX.md

COMPONENTS.md

```



Spiegare:



\* struttura;

\* routing;

\* component architecture;

\* design tokens;

\* API integration;

\* testing.



\---



\# 118. Storybook



Utilizzare Storybook se utile per il design system.



Creare story per componenti principali:



```text

Button

Card

Dialog

DataTable

MoneyValue

TransactionRow

MetricCard

EmptyState

ErrorState

```



Non è obbligatorio introdurlo immediatamente se aumenta inutilmente la complessità.



\---



\# 119. Frontend Definition of Done



Una pagina è completa solamente quando contiene:



\* layout desktop;

\* layout mobile;

\* loading state;

\* error state;

\* empty state;

\* success state quando necessario;

\* accessibilità;

\* responsive behavior;

\* API integration;

\* test;

\* gestione degli errori;

\* navigazione;

\* feedback utente.



\---



\# 120. Frontend Development Process



Procedere per vertical slices.



Non sviluppare prima 50 componenti astratti e poi l'applicazione.



Ordine consigliato:



```text

1\. Design system foundation

2\. App shell

3\. Authentication

4\. Dashboard

5\. Accounts

6\. Transactions

7\. Import Wizard

8\. Expenses

9\. Income

10\. Net Worth

11\. Investments

12\. Settings

13\. Integrations

14\. Mobile optimization

15\. Accessibility

16\. Performance

17\. Visual regression

```



\---



\# 121. Design System First



Prima di implementare tutte le pagine:



creare:



```text

Typography

Colors

Spacing

Buttons

Inputs

Cards

Tables

Dialogs

Drawers

Badges

Charts

Navigation

```



Poi utilizzarli per costruire le pagine.



\---



\# 122. Dashboard First



La prima vera pagina completa deve essere la Dashboard.



Deve essere utilizzata come riferimento per:



\* spacing;

\* typography;

\* cards;

\* charts;

\* responsive behavior;

\* visual hierarchy.



\---



\# 123. Mobile First



Implementare inizialmente il layout mobile e poi espanderlo a desktop quando possibile.



Non trattare mobile come una versione secondaria.



\---



\# 124. Frontend Quality Rules



Non accettare:



\* componenti enormi;

\* prop drilling incontrollato;

\* fetch duplicati;

\* API calls nei componenti senza abstraction;

\* CSS duplicato;

\* stringhe hardcoded;

\* accessibilità ignorata;

\* layout desktop-only;

\* grafici non responsive;

\* loading spinner ovunque;

\* errori tecnici mostrati direttamente all'utente.



\---



\# 125. Integration with Backend



Il frontend deve rispettare il contratto API definito dal backend.



Non inventare endpoint.



Se manca un endpoint necessario:



```text

BACKEND API REQUIRED

```



documentare:



\* endpoint;

\* method;

\* request;

\* response;

\* authorization;

\* error cases.



Non implementare workaround fragili nel frontend.



\---



\# 126. Backend/Frontend Contract



Per ogni feature importante definire:



```text

Frontend

&#x20;  ↓

API Contract

&#x20;  ↓

Backend

&#x20;  ↓

Database

```



Il frontend deve consumare dati tipizzati.



Generare eventualmente TypeScript types/client dall'OpenAPI backend.



\---



\# 127. Final Product Experience



L'esperienza finale deve essere:



```text

Open Lumio

&#x20;    ↓

Capisco subito la mia situazione finanziaria

&#x20;    ↓

Posso esplorare il patrimonio

&#x20;    ↓

Posso capire dove spendo

&#x20;    ↓

Posso vedere i miei investimenti

&#x20;    ↓

Posso importare nuovi dati

&#x20;    ↓

Lumio automatizza il lavoro

```



L'utente non deve avere bisogno di conoscere:



\* PostgreSQL;

\* Docker;

\* AI;

\* LLM;

\* parser;

\* API;

\* worker;

\* Redis.



Queste sono complessità interne.



\---



\# 128. Core UX Principle



La complessità deve stare nel software, non nella testa dell'utente.



> \*\*Lumio should make financial complexity feel simple.\*\*



\---



\# 129. Final Development Rule



Non costruire una semplice collection di pagine.



Costruire un prodotto coerente.



Ogni nuova funzionalità deve rispettare:



```text

Brand

UX

Design System

Navigation

Accessibility

Responsive behavior

API contract

Security

Performance

```



Se una nuova feature richiede una modifica al design system, aggiornare prima il design system e poi utilizzare il componente nella feature.



Non creare eccezioni grafiche locali.



\---



\# 130. Final Objective



Il frontend finale di Lumio deve permettere a un utente di:



\* comprendere il proprio patrimonio;

\* analizzare spese e entrate;

\* consultare tutti i propri conti;

\* esplorare i movimenti;

\* importare documenti;

\* correggere classificazioni;

\* utilizzare AI locale o cloud opzionale;

\* analizzare investimenti;

\* visualizzare il portfolio;

\* esportare i propri dati;

\* utilizzare l'applicazione comodamente da smartphone.



Il risultato deve essere percepito come una \*\*moderna fintech personale\*\*, non come un frontend tecnico costruito sopra una REST API.



Prima di implementare una nuova pagina, definire:



1\. scopo della pagina;

2\. informazioni principali;

3\. azione primaria;

4\. azioni secondarie;

5\. stato loading;

6\. stato empty;

7\. stato error;

8\. responsive behavior;

9\. accessibilità;

10\. API necessarie.



Procedere per vertical slices e mantenere il prodotto funzionante dopo ogni milestone.




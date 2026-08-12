\# LUMIO — PRODUCT SPECIFICATION



\## Product Vision, Functional Requirements \& User Experience



\---



\# 1. Product Identity



\## Nome



\*\*Lumio\*\*



\## Concept



Lumio è una piattaforma personale di \*\*financial management e wealth management\*\*, progettata per raccogliere, normalizzare, categorizzare e visualizzare in modo semplice e intelligente i dati finanziari personali dell'utente.



Lumio deve permettere di trasformare dati provenienti da:



\* conti correnti;

\* carte;

\* broker;

\* estratti conto PDF;

\* CSV;

\* altri documenti finanziari;



in una rappresentazione unica, coerente e facilmente consultabile del proprio patrimonio.



\---



\# 2. Vision



La visione di Lumio è:



> \*\*Rendere semplice capire dove sono, dove vanno e come stanno evolvendo i propri soldi.\*\*



Lumio non deve limitarsi a mostrare transazioni.



Deve aiutare l'utente a comprendere:



\* quanto possiede;

\* quanto spende;

\* quanto guadagna;

\* quanto risparmia;

\* dove spende;

\* come evolve il patrimonio;

\* come è composto il portfolio;

\* come stanno andando gli investimenti;

\* quali sono i principali cambiamenti nel tempo.



\---



\# 3. Core Philosophy



Lumio deve seguire un principio fondamentale:



> \*\*La complessità deve stare nel software, non nella testa dell'utente.\*\*



L'utente non deve sapere:



\* come viene analizzato un PDF;

\* quale parser viene utilizzato;

\* quale LLM viene utilizzato;

\* come vengono categorizzati i movimenti;

\* quale database contiene i dati;

\* come funziona il backend;

\* come funzionano i worker.



Deve semplicemente poter dire:



> "Ho questo estratto conto. Voglio aggiungerlo a Lumio."



\---



\# 4. Target Users



Lumio deve essere progettato principalmente per tre categorie.



\## 4.1 Personal User



Persona che vuole:



\* controllare le spese;

\* vedere il patrimonio;

\* organizzare i conti;

\* analizzare le proprie finanze.



Non necessariamente esperta di tecnologia.



\---



\## 4.2 Power User



Utente che desidera:



\* self-hosting;

\* controllo dei dati;

\* database PostgreSQL esterno;

\* AI locale;

\* Ollama;

\* esportazioni;

\* API;

\* integrazioni;

\* automazioni.



\---



\## 4.3 Advanced Financial User



Utente che possiede:



\* più conti;

\* più broker;

\* investimenti;

\* ETF;

\* azioni;

\* liquidità;

\* patrimonio distribuito su più istituzioni.



Per questo utente Lumio deve poter diventare un vero \*\*personal wealth dashboard\*\*.



\---



\# 5. Privacy Philosophy



Lumio nasce con una forte attenzione alla privacy.



I dati finanziari sono altamente sensibili.



Principio:



> \*\*I dati dell'utente appartengono all'utente.\*\*



L'applicazione deve essere progettata in modo che, per impostazione predefinita:



\* ogni utente veda solamente i propri dati;

\* nessun utente possa accedere ai dati di un altro;

\* i dati siano logicamente isolati;

\* le API verifichino sempre l'autorizzazione;

\* il frontend non possa bypassare i controlli backend.



\---



\# 6. Self-Hosted First



Lumio deve essere pensato prima di tutto come applicazione self-hosted.



L'utente deve poter installare:



```text

Lumio

\+

Docker

\+

Database

```



senza dover configurare manualmente decine di servizi.



La configurazione semplice deve essere possibile tramite Docker Compose.



\---



\# 7. Power User Configuration



Gli utenti esperti devono poter configurare:



\* PostgreSQL esterno;

\* database host;

\* porta;

\* username;

\* password;

\* SSL;

\* AI provider;

\* Ollama;

\* provider cloud;

\* storage;

\* altri parametri avanzati.



La configurazione avanzata non deve complicare l'installazione base.



\---



\# 8. Multi-Tenancy



Lumio deve essere multi-user.



Ogni utente possiede un proprio spazio dati.



Concettualmente:



```text

User A

&#x20;├── Accounts

&#x20;├── Transactions

&#x20;├── Investments

&#x20;├── Imports

&#x20;└── Settings



User B

&#x20;├── Accounts

&#x20;├── Transactions

&#x20;├── Investments

&#x20;├── Imports

&#x20;└── Settings

```



User A non deve poter vedere:



```text

User B

```



in alcuna circostanza.



L'isolamento deve essere applicato:



\* API;

\* service layer;

\* database queries;

\* authorization;

\* eventuali job asincroni.



\---



\# 9. Financial Data Model



Il sistema deve distinguere almeno:



```text

Accounts

Transactions

Categories

Merchants

Imports

Assets

Positions

Portfolios

Balances

Rules

AI Classifications

```



Il modello deve essere sufficientemente astratto da supportare diversi istituti finanziari.



\---



\# 10. Institutions



Lumio deve utilizzare un concetto di:



\*\*Institution / Provider\*\*



Esempi:



```text

Trade Republic

BancoPosta

Fineco

Revolut

ING

```



L'istituto non deve determinare rigidamente il modello dati.



Deve essere possibile aggiungere nuovi provider attraverso adapter/parser dedicati.



\---



\# 11. Import Philosophy



L'importazione dei dati è una funzione fondamentale.



Lumio deve poter ricevere documenti finanziari e trasformarli in dati strutturati.



Pipeline concettuale:



```text

Document

&#x20;  ↓

Detection

&#x20;  ↓

Parsing

&#x20;  ↓

Normalization

&#x20;  ↓

Validation

&#x20;  ↓

Classification

&#x20;  ↓

User Review

&#x20;  ↓

Persistence

```



\---



\# 12. Supported Documents



Versione iniziale:



\* PDF.



Architettura predisposta per:



\* CSV;

\* XLSX;

\* OFX;

\* CAMT;

\* altri formati.



\---



\# 13. Provider Adapters



Ogni istituto può avere un parser dedicato.



Esempio:



```text

providers/

├── trade\_republic/

├── banco\_posta/

├── fineco/

└── generic/

```



Ogni adapter deve convertire il documento originale in un modello normalizzato.



\---



\# 14. Trade Republic



Trade Republic deve essere uno dei primi provider supportati.



Il sistema deve poter riconoscere automaticamente il formato del documento quando possibile.



L'utente non dovrebbe essere obbligato a selezionare manualmente il provider se il documento può essere identificato.



\---



\# 15. Future Providers



L'architettura deve permettere di aggiungere successivamente:



\* BancoPosta;

\* Fineco;

\* Revolut;

\* N26;

\* ING;

\* altri broker e banche.



Aggiungere un nuovo provider non deve richiedere modifiche invasive al core.



\---



\# 16. Transaction Model



Una transazione deve poter contenere almeno:



```text

id

account

date

value\_date

description

merchant

amount

currency

type

category

subcategory

status

source

confidence

created\_at

updated\_at

```



Il modello può evolvere.



\---



\# 17. Transaction Types



Supportare almeno:



```text

Income

Expense

Transfer

Investment

Dividend

Interest

Fee

Refund

Unknown

```



\---



\# 18. Internal Transfers



I trasferimenti tra conti appartenenti allo stesso utente devono essere riconosciuti quando possibile.



Esempio:



```text

Trade Republic

\- €1.000



BancoPosta

\+ €1.000

```



non deve essere contabilizzato come:



```text

\- €1.000 di spesa

\+ €1.000 di entrata

```



ma come:



```text

Internal Transfer

```



\---



\# 19. Categories



Lumio deve avere categorie predefinite.



Esempio:



```text

Casa

Alimentari

Trasporti

Ristoranti

Shopping

Abbonamenti

Salute

Viaggi

Intrattenimento

Istruzione

Tasse

Investimenti

Entrate

Altro

```



L'utente deve poter personalizzare il sistema.



\---



\# 20. Category Hierarchy



Supportare:



```text

Alimentari

&#x20;├── Supermercato

&#x20;├── Mercato

&#x20;└── Delivery

```



e:



```text

Casa

&#x20;├── Affitto

&#x20;├── Bollette

&#x20;└── Manutenzione

```



\---



\# 21. Rules



L'utente deve poter creare regole.



Esempio:



```text

IF merchant = "LIDL"

THEN category = "Alimentari/Supermercato"

```



Le regole devono poter avere priorità.



\---



\# 22. Automatic Classification



Lumio deve supportare più livelli di classificazione:



```text

1\. User

2\. Rules

3\. Deterministic system logic

4\. AI

5\. Unknown

```



La classificazione deve essere tracciabile.



\---



\# 23. AI Is Optional



L'AI NON deve essere obbligatoria.



Lumio deve funzionare anche senza AI.



Modalità:



```text

AI Disabled

```



In questa modalità utilizzare:



\* parser;

\* regole;

\* merchant mapping;

\* classificazione deterministica.



\---



\# 24. AI Providers



Supportare concettualmente:



```text

Disabled

Local model

Ollama

OpenAI

Anthropic

Custom endpoint

```



L'architettura deve essere provider-agnostic.



\---



\# 25. Local AI



L'utente deve poter utilizzare un modello locale.



Esempio:



```text

Lumio

&#x20;↓

Ollama

&#x20;↓

Gemma

```



La configurazione deve essere opzionale.



\---



\# 26. AI Confidence



Quando l'AI classifica una transazione, deve poter restituire una confidence.



Esempio:



```text

Shopping

92%

```



La confidence deve essere utilizzata per decidere se:



\* accettare automaticamente;

\* chiedere revisione.



\---



\# 27. Human in the Loop



L'utente deve poter correggere le classificazioni.



Quando una classificazione è incerta:



```text

AI suggestion

↓

User review

↓

Confirmed classification

```



La correzione dell'utente deve avere priorità rispetto all'AI.



\---



\# 28. Learning Through Rules



Quando l'utente corregge ripetutamente lo stesso merchant, Lumio può suggerire:



> "Vuoi creare una regola per i prossimi movimenti?"



Non è necessario che il sistema implementi machine learning proprietario.



Le regole deterministiche sono preferibili quando sufficienti.



\---



\# 29. Financial Overview



La dashboard deve permettere di comprendere rapidamente:



```text

Net Worth

Cash

Investments

Income

Expenses

Cash Flow

```



\---



\# 30. Net Worth



Formula concettuale:



```text

Net Worth =

Assets - Liabilities

```



Versione iniziale può partire da:



```text

Cash

\+

Investments

\+

Other Assets

\-

Liabilities

```



\---



\# 31. Net Worth History



Salvare o ricostruire lo storico del patrimonio.



L'utente deve poter vedere:



```text

1M

3M

6M

YTD

1Y

ALL

```



\---



\# 32. Cash Flow



Calcolare:



```text

Income

\-

Expenses

=

Cash Flow

```



Escludere i trasferimenti interni dal calcolo quando appropriato.



\---



\# 33. Expense Analytics



Lumio deve permettere di analizzare:



\* totale spese;

\* spese per categoria;

\* spese per merchant;

\* spese nel tempo;

\* variazioni;

\* ricorrenze.



\---



\# 34. Income Analytics



Analizzare:



\* stipendio;

\* freelance;

\* dividendi;

\* interessi;

\* altri redditi.



\---



\# 35. Portfolio



Il portfolio deve poter aggregare investimenti provenienti da più conti.



Esempio:



```text

Trade Republic

Fineco

Degiro

```



→



```text

Total Portfolio

```



\---



\# 36. Portfolio Allocation



Supportare almeno:



```text

ETF

Stocks

Bonds

Cash

Crypto

Other

```



Il sistema deve essere estensibile.



\---



\# 37. Investment Performance



Visualizzare:



\* valore;

\* costo;

\* profit/loss;

\* rendimento;

\* storico.



La precisione dei calcoli deve essere una priorità.



\---



\# 38. Account vs Portfolio



Distinguere:



```text

Account

```



da:



```text

Portfolio

```



Un account può contenere:



\* cash;

\* securities;

\* transactions.



Un portfolio è una vista aggregata.



\---



\# 39. Data Aggregation



L'utente deve poter passare da:



```text

Singolo conto

```



a:



```text

Tutti i conti

```



senza duplicare i dati.



\---



\# 40. Dashboard Filters



I principali filtri devono poter essere:



```text

Time

Account

Category

Type

```



e in futuro:



```text

Institution

Currency

Portfolio

```



\---



\# 41. Data Integrity



Il sistema deve evitare:



\* duplicazione accidentale;

\* import duplicati;

\* doppio conteggio trasferimenti;

\* transazioni corrotte.



\---



\# 42. Duplicate Detection



Durante l'importazione identificare potenziali duplicati.



Possibili segnali:



```text

same date

same amount

same description

same account

```



Il sistema deve poter segnalare:



> "Questo movimento potrebbe essere già presente."



\---



\# 43. Import Idempotency



Importare due volte lo stesso documento non dovrebbe creare automaticamente un doppio set di transazioni.



Il sistema deve implementare meccanismi di idempotenza/deduplicazione.



\---



\# 44. Original Data Preservation



Quando possibile, mantenere:



\* documento originale;

\* dati estratti;

\* dati normalizzati;

\* classificazione.



Non perdere l'informazione originale.



\---



\# 45. Auditability



Le modifiche importanti devono poter essere ricostruite.



Esempio:



```text

Imported

→ AI classified

→ User changed category

→ Rule created

```



\---



\# 46. Import Jobs



L'elaborazione dei documenti deve essere asincrona.



Concept:



```text

Upload

&#x20;↓

Job

&#x20;↓

Processing

&#x20;↓

Progress

&#x20;↓

Completed

```



\---



\# 47. Realtime Progress



Il frontend deve poter ricevere eventi:



```text

started

progress

warning

completed

failed

```



Preferire:



```text

SSE

```



o:



```text

WebSocket

```



rispetto al polling continuo quando tecnicamente appropriato.



\---



\# 48. Job Failure



Se un import fallisce:



l'utente deve sapere:



\* cosa è successo;

\* in quale fase;

\* se i dati sono stati salvati;

\* cosa può fare.



Mai lasciare un job nello stato ambiguo.



\---



\# 49. Import Review



Gli errori di classificazione non devono necessariamente bloccare l'intero import.



Esempio:



```text

327 transactions

319 classified

8 need review

```



L'import può essere completato con 8 elementi da verificare.



\---



\# 50. Google Sheets



Google Sheets è una \*\*integrazione opzionale\*\*.



Non deve essere necessario per utilizzare Lumio.



Lumio deve avere una propria interfaccia completa per:



\* consultazione;

\* analisi;

\* grafici;

\* gestione.



Google Sheets è un export/integration layer.



\---



\# 51. Export



Supportare:



```text

CSV

XLSX

JSON

Google Sheets

```



quando implementati.



\---



\# 52. Data Ownership



L'utente deve poter esportare i propri dati.



Il sistema non deve creare lock-in intenzionale.



\---



\# 53. No Vendor Lock-in



Lumio deve essere indipendente da:



\* un singolo cloud AI;

\* Google Sheets;

\* un singolo database;

\* un singolo provider finanziario.



\---



\# 54. Architecture Independence



La Product Specification non deve imporre:



\* React;

\* FastAPI;

\* PostgreSQL;

\* Redis;

\* Ollama.



Queste decisioni appartengono ai documenti tecnici.



\---



\# 55. UX Independence



La product logic deve essere mantenuta anche se il frontend viene successivamente riscritto.



Il comportamento del prodotto deve essere definito a livello funzionale.



\---



\# 56. Mobile



Lumio deve essere utilizzabile da smartphone.



La versione mobile deve permettere almeno:



\* dashboard;

\* conti;

\* transazioni;

\* import;

\* portfolio;

\* patrimonio;

\* impostazioni principali.



\---



\# 57. PWA



La web app deve essere progettata in modo da poter diventare una PWA.



Una futura app nativa non deve richiedere di riprogettare il backend.



\---



\# 58. Future Native Apps



In futuro potranno essere sviluppate:



```text

iOS

Android

```



utilizzando le stesse API backend.



La Product Specification deve quindi evitare comportamenti dipendenti esclusivamente dal browser.



\---



\# 59. Multi-Currency



Architettura predisposta per:



```text

EUR

USD

GBP

CHF

```



e altre valute.



La valuta originale della transazione deve essere preservata.



\---



\# 60. Currency Conversion



In futuro il sistema potrà utilizzare exchange rate per aggregare patrimoni multi-currency.



Non modificare il valore originale.



Esempio:



```text

Original:

$1,000 USD



Converted:

€X

```



\---



\# 61. Multiple Accounts



L'utente deve poter avere:



```text

Trade Republic

BancoPosta

Fineco

Revolut

```



contemporaneamente.



\---



\# 62. Account Lifecycle



Un conto può essere:



```text

Active

Archived

Closed

```



Chiudere/archiviare un conto non deve eliminare automaticamente la cronologia.



\---



\# 63. Transaction Lifecycle



Una transazione può essere:



```text

Imported

Classified

Reviewed

Confirmed

Excluded

```



\---



\# 64. Excluded Transactions



Permettere di escludere transazioni dall'analisi senza necessariamente cancellarle.



Esempio:



```text

Transfer

Duplicate

Test

Personal exclusion

```



\---



\# 65. Recurring Transactions



In futuro riconoscere:



```text

Netflix

Spotify

Rent

Salary

Insurance

```



e visualizzare:



```text

Recurring Expenses

Recurring Income

```



\---



\# 66. Financial Insights



In futuro Lumio può generare insight come:



> "Le tue spese alimentari sono aumentate del 18% rispetto alla media degli ultimi sei mesi."



oppure:



> "Il tuo risparmio medio mensile è di €1.150."



Gli insight devono essere:



\* comprensibili;

\* verificabili;

\* basati sui dati;

\* non manipolativi.



\---



\# 67. AI Insights



Gli insight AI sono opzionali.



Non devono diventare indispensabili per comprendere i dati.



Prima vengono:



```text

accurate calculations

```



poi:



```text

AI interpretation

```



\---



\# 68. No Financial Advice



Lumio deve distinguere chiaramente:



```text

Financial data

```



da:



```text

Financial advice

```



L'applicazione deve evitare di presentare automaticamente suggerimenti finanziari come verità professionali.



\---



\# 69. Data Visualization Philosophy



I grafici devono rispondere a domande.



Non creare grafici solamente perché "sono belli".



Esempi:



```text

Quanto possiedo?

Come sta cambiando?

Dove spendo?

Quanto risparmio?

Come è distribuito il portfolio?

```



\---



\# 70. Dashboard Philosophy



La dashboard non deve essere un muro di widget.



Deve avere gerarchia:



```text

1\. Patrimonio

2\. Cash Flow

3\. Spese

4\. Investimenti

5\. Attività recenti

```



\---



\# 71. First-Time User



Un nuovo utente senza dati deve vedere una dashboard vuota ma utile.



Esempio:



```text

Benvenuto in Lumio.



Inizia importando il tuo primo estratto conto.



\[Importa PDF]

```



Non mostrare grafici vuoti senza significato.



\---



\# 72. Power User Experience



L'utente esperto deve poter accedere a:



\* impostazioni avanzate;

\* API;

\* AI;

\* database configuration;

\* integrations;

\* export.



La complessità avanzata deve essere nascosta dall'esperienza base.



\---



\# 73. Simplicity Principle



Default:



```text

Simple

```



Advanced:



```text

Configurable

```



Mai:



```text

Complex by default

```



\---



\# 74. Data Import Transparency



Durante un import l'utente deve poter sapere:



```text

What was detected

What was extracted

What was classified

What requires attention

```



\---



\# 75. Provider Detection



Quando possibile:



```text

PDF

&#x20;↓

Trade Republic detected

```



Se confidence bassa:



```text

Non siamo sicuri del provider.



\[Trade Republic]

\[BancoPosta]

\[Altro]

```



\---



\# 76. Generic Parser



Prevedere un parser generico per documenti non riconosciuti.



Il sistema deve poter estrarre dati basilari quando il formato lo consente.



\---



\# 77. Parser Extensibility



Ogni parser deve essere un modulo indipendente.



Aggiungere un nuovo provider non deve richiedere modifiche al database core.



\---



\# 78. Versioning



I parser devono poter essere versionati.



Esempio:



```text

Trade Republic parser v1

Trade Republic parser v2

```



Questo permette di gestire modifiche future nei documenti.



\---



\# 79. Schema Evolution



Il database deve poter evolvere senza distruggere dati esistenti.



Utilizzare migrations.



\---



\# 80. API Evolution



Le API devono poter evolvere mantenendo compatibilità quando possibile.



\---



\# 81. User Experience of Updates



Aggiornare Lumio non deve normalmente richiedere all'utente di riconfigurare tutto.



Docker image update:



```text

pull

→ restart

→ migrations

→ application

```



\---



\# 82. Database Initialization



Installazione base:



```text

docker compose up

```



deve poter inizializzare il database.



Per utenti power:



```text

EXTERNAL\_POSTGRES

```



deve essere supportato.



\---



\# 83. Configuration Philosophy



Configurazione semplice:



```text

.env

```



Configurazione avanzata:



```text

external services

```



Non richiedere manualmente SQL all'utente medio.



\---



\# 84. Observability



Il sistema deve poter fornire:



\* logs;

\* health status;

\* job status;

\* database status;

\* AI provider status.



La UI amministrativa può essere aggiunta in futuro.



\---



\# 85. Error Philosophy



Gli errori devono essere:



\* comprensibili;

\* specifici;

\* recuperabili quando possibile.



Mai:



> "Internal Server Error"



come unico messaggio all'utente.



\---



\# 86. Reliability



Per dati finanziari:



> \*\*Correctness > Convenience\*\*



È preferibile chiedere una conferma in più piuttosto che alterare silenziosamente un dato finanziario.



\---



\# 87. Transaction Accuracy



L'importo originale estratto deve essere preservato.



Le trasformazioni devono essere tracciabili.



\---



\# 88. Decimal Precision



I calcoli finanziari non devono basarsi su floating point non controllato.



Utilizzare precisione decimale appropriata.



\---



\# 89. Time Zones



Conservare correttamente date e timestamp.



La data finanziaria della transazione non deve essere alterata solamente perché l'utente cambia timezone.



\---



\# 90. Financial Periods



Supportare analisi:



```text

Daily

Weekly

Monthly

Quarterly

Yearly

Custom

```



\---



\# 91. Reporting



In futuro Lumio potrà generare:



\* report mensili;

\* report annuali;

\* PDF;

\* XLSX;

\* riepiloghi.



Non necessario nella prima versione.



\---



\# 92. Future Budgeting



L'architettura deve poter supportare in futuro:



```text

Budget

Actual

Variance

```



senza rendere il budgeting obbligatorio.



\---



\# 93. Future Goals



Possibile supporto futuro:



```text

Emergency Fund

Travel

House

Investment Goal

```



\---



\# 94. Future Net Worth Forecast



In futuro:



```text

Historical

\+

Assumptions

=

Forecast

```



ma non implementare previsioni speculative nella prima versione.



\---



\# 95. Future Family / Shared Finance



L'architettura può supportare in futuro:



```text

Personal

Family

Shared accounts

```



ma la separazione dei dati personali deve rimanere rigorosa.



\---



\# 96. Roles



In futuro:



```text

Owner

Admin

Member

Viewer

```



\---



\# 97. No Premature Complexity



La prima versione non deve implementare tutto.



Priorità:



```text

Import

→ Normalize

→ Classify

→ Store

→ Visualize

```



\---



\# 98. MVP



Il Minimum Viable Product deve permettere:



\### Authentication



\* user registration;

\* login;

\* logout.



\### Accounts



\* create;

\* view;

\* archive.



\### Import



\* PDF upload;

\* provider detection;

\* parser;

\* extraction;

\* deduplication;

\* classification.



\### Transactions



\* list;

\* search;

\* filter;

\* edit;

\* categorize.



\### Dashboard



\* net worth;

\* income;

\* expenses;

\* cash flow;

\* transaction overview.



\### Categories



\* default categories;

\* custom categories;

\* rules.



\### AI



\* optional;

\* local/cloud provider abstraction.



\### Export



\* CSV almeno.



\---



\# 99. MVP Exclusions



Non rendere obbligatori nella prima versione:



\* budgeting avanzato;

\* financial advice;

\* complex forecasting;

\* family sharing;

\* mobile native apps;

\* banking APIs;

\* automatic bank synchronization;

\* sophisticated tax management.



\---



\# 100. Product Roadmap



\## Phase 1 — Foundation



```text

Authentication

Database

Accounts

Transactions

Categories

```



\## Phase 2 — Import



```text

PDF

Trade Republic

Parser

Normalization

Deduplication

```



\## Phase 3 — Intelligence



```text

Rules

AI optional

Classification

Review

```



\## Phase 4 — Analytics



```text

Dashboard

Expenses

Income

Cash Flow

Net Worth

```



\## Phase 5 — Investments



```text

Portfolio

Positions

Performance

Allocation

```



\## Phase 6 — Integrations



```text

Google Sheets

CSV

XLSX

```



\## Phase 7 — Expansion



```text

BancoPosta

Fineco

Revolut

Other providers

```



\---



\# 101. Definition of Product Success



Lumio può essere considerato riuscito quando un nuovo utente può:



```text

1\. Registrarsi

2\. Accedere

3\. Caricare un estratto conto

4\. Attendere l'elaborazione

5\. Controllare le classificazioni

6\. Confermare

7\. Tornare alla dashboard

8\. Capire immediatamente la propria situazione finanziaria

```



senza bisogno di assistenza tecnica.



\---



\# 102. Product Quality Bar



Lumio deve essere:



\### Semplice



Un utente normale deve poterlo utilizzare.



\### Potente



Un power user deve poterlo configurare profondamente.



\### Privato



I dati devono rimanere sotto il controllo dell'utente.



\### Estensibile



Nuovi provider devono poter essere aggiunti.



\### Intelligente



L'automazione deve ridurre il lavoro manuale.



\### Trasparente



L'utente deve poter capire cosa il sistema ha fatto.



\### Bello



L'interfaccia deve essere piacevole da usare.



\### Affidabile



I dati finanziari devono essere trattati con la massima accuratezza.



\---



\# 103. Ultimate Product Principle



Lumio non deve essere:



> "Un software che importa estratti conto."



Deve diventare:



> \*\*"Il posto in cui l'utente comprende il proprio patrimonio."\*\*



L'importazione PDF è il punto di ingresso.



Il vero prodotto è:



```text

Financial Data

&#x20;      ↓

Lumio

&#x20;      ↓

Understanding

&#x20;      ↓

Better Financial Awareness

```



\---



\# 104. Final Product Statement



\*\*Lumio\*\* è una piattaforma self-hosted, privacy-first e intelligente per organizzare, comprendere e analizzare le proprie finanze.



Raccoglie dati provenienti da conti e investimenti, li normalizza, li categorizza e li presenta attraverso una moderna esperienza web.



L'AI è un acceleratore opzionale, non una dipendenza.



Google Sheets è un'integrazione opzionale, non il prodotto.



Il database è un dettaglio infrastrutturale, non un elemento dell'esperienza utente.



Il PDF è solamente il punto di ingresso.



Il vero obiettivo di Lumio è:



> \*\*dare all'utente una visione chiara, completa e privata della propria situazione finanziaria.\*\*



\---



\# 105. Guiding Sentence



Ogni decisione futura sul prodotto deve poter essere verificata contro questa domanda:



> \*\*"Questa scelta rende più semplice per l'utente capire e gestire il proprio denaro?"\*\*



Se la risposta è no, la funzionalità deve essere ripensata.




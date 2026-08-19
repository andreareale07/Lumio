# LUMIO — IMPLEMENTAZIONE ROBUSTA DEL SISTEMA DI DEDUPLICAZIONE DELLE TRANSAZIONI

## CONTESTO

Lumio è un gestionale finanziario multi-utente che consente di importare estratti conto bancari, principalmente tramite PDF e CSV.

Il progetto dispone già di:

- backend Python/FastAPI;
- PostgreSQL;
- Redis/worker per elaborazioni asincrone;
- sistema multi-tenant/workspace;
- Row-Level Security;
- modello `financial_accounts`;
- modello `transactions`;
- modello `imports`;
- BankParser astratto;
- parser Trade Republic;
- `description_raw`;
- `description_normalized`;
- `transaction_date`;
- `transaction_type`;
- Rules Engine;
- eventuale AI opzionale;
- UI per l'importazione e il monitoraggio dei job.

Il sistema deve essere modificato per introdurre un vero e proprio Transaction Deduplication Engine.

## OBIETTIVO PRINCIPALE

Impedire che lo stesso movimento finanziario venga importato più volte quando l'utente carica estratti conto sovrapposti.

Esempio:

Import precedente:

    gennaio → marzo

Nuovo PDF:

    febbraio → luglio

Il nuovo PDF contiene anche tutti i movimenti di febbraio e marzo già presenti nel database.

Il risultato desiderato è:

    movimenti già presenti → non duplicare
    movimenti nuovi → importare
    casi ambigui → chiedere all'utente

Il sistema deve essere molto conservativo.

L'integrità dei dati finanziari ha priorità assoluta.

NON è accettabile eliminare automaticamente una transazione reale perché un algoritmo l'ha erroneamente considerata duplicata.

---

# 1. PRIMA FASE OBBLIGATORIA: ANALISI DEL REPOSITORY

PRIMA DI MODIFICARE IL CODICE:

1. analizza completamente il repository;
2. identifica i modelli SQLAlchemy esistenti;
3. identifica lo schema PostgreSQL;
4. analizza migrations Alembic;
5. analizza `transactions`;
6. analizza `imports`;
7. analizza l'attuale Import Engine;
8. analizza tutti i BankParser;
9. analizza il Trade Republic parser;
10. analizza il Rules Engine;
11. analizza i job asincroni;
12. analizza le API coinvolte nell'import;
13. analizza la UI dell'import;
14. analizza i test esistenti;
15. verifica come vengono gestiti `description_raw` e `description_normalized`;
16. verifica come viene utilizzato `transaction_date`;
17. verifica se il campo saldo/balance è già presente nel modello;
18. verifica se esistono già meccanismi di deduplicazione.

NON assumere che lo schema attuale sia identico a quello descritto in questo prompt.

Adatta la soluzione all'architettura realmente presente nel repository.

---

# 2. PRIMA DI IMPLEMENTARE: PRODURRE UN PIANO TECNICO

Dopo l'analisi del repository devi produrre un piano tecnico dettagliato.

Il piano deve descrivere:

- modifiche al database;
- nuove tabelle eventualmente necessarie;
- nuove colonne;
- indici;
- migration Alembic;
- modifiche ai domain model;
- modifiche all'Import Engine;
- algoritmo di deduplicazione;
- gestione delle transazioni identiche;
- gestione dei casi ambigui;
- API necessarie;
- modifiche UI;
- gestione delle decisioni manuali;
- strategia di test;
- eventuali problemi di compatibilità.

NON procedere immediatamente con una riscrittura dell'architettura.

Privilegiare modifiche minime e coerenti con il progetto esistente.

Dopo aver prodotto il piano, procedere all'implementazione.

---

# 3. PRINCIPIO FONDAMENTALE

Il sistema NON deve considerare automaticamente duplicato un record solamente perché esiste un altro record con lo stesso fingerprint.

Questo è fondamentale perché possono esistere transazioni legittimamente identiche.

Esempio:

    19/08/2026 | Netflix | -12,99 EUR | expense
    19/08/2026 | Netflix | -12,99 EUR | expense

potrebbero essere due transazioni reali distinte.

Pertanto:

NON creare una UNIQUE constraint sul fingerprint.

Il fingerprint deve essere indicizzato, non reso univoco.

---

# 4. IDENTITÀ DETERMINISTICA DELLA TRANSAZIONE

Per PDF/CSV la candidata principale all'identità deve essere costruita usando almeno:

    workspace_id
    account_id
    transaction_date
    amount
    currency
    description_normalized
    transaction_type

`transaction_date` è la data bancaria definitiva del movimento.

Nel caso Trade Republic corrisponde alla colonna:

    DATA

Nel database Lumio il campo è:

    transaction_date

NON utilizzare una data diversa se `transaction_date` è già il dato ufficiale utilizzato dal dominio.

---

# 5. FINGERPRINT

Creare un fingerprint deterministico derivato dai campi di identità.

Esempio concettuale:

    SHA-256(
        canonical_workspace/account scope +
        account_id +
        transaction_date +
        canonical_amount +
        currency +
        description_normalized +
        transaction_type
    )

Il formato esatto deve essere scelto in base alle convenzioni del progetto.

IMPORTANTE:

- canonicalizzare sempre i valori prima dell'hash;
- importi devono avere rappresentazione deterministica;
- evitare problemi di floating point;
- usare Decimal/numeric;
- normalizzare la currency;
- normalizzare la data;
- evitare collisioni dovute a concatenazioni ambigue;
- utilizzare un encoding strutturato/deterministico.

NON utilizzare float per costruire il fingerprint.

---

# 6. SCOPE DEL FINGERPRINT

Il fingerprint deve essere scoped almeno per:

    workspace
    account

Una transazione su Account A non deve mai essere considerata la stessa transazione di Account B solamente perché ha:

    stessa data
    stessa descrizione
    stesso importo
    stesso tipo

Il multi-tenancy deve rimanere completamente isolato.

RLS e authorization devono continuare a essere rispettati.

---

# 7. CURRENCY

Non usare un LLM per determinare la currency.

La currency deve essere determinata tramite una gerarchia deterministica.

Preferenza:

1. currency esplicitamente estratta dal parser/documento;
2. currency configurata sul financial account;
3. altra fonte deterministica già presente nell'architettura;
4. se non è possibile determinarla in modo affidabile → record da REVIEW.

NON fare inferenza AI della valuta.

Il sistema deve evitare di inventare una currency.

Analizzare come il parser Trade Republic identifica attualmente la valuta.

---

# 8. DESCRIPTION RAW / NORMALIZED

Lumio dispone già di:

    description_raw
    description_normalized

Mantenerli distinti.

`description_raw` deve rappresentare il dato originale estratto dal documento.

`description_normalized` deve essere usata per matching e fingerprint.

La normalizzazione deve essere CONSERVATIVA.

Sono ammesse trasformazioni deterministiche come:

- trim;
- lowercase;
- normalizzazione Unicode;
- normalizzazione degli spazi;
- rimozione di differenze puramente tipografiche non informative.

NON effettuare normalizzazioni aggressive.

NON eliminare arbitrariamente numeri, codici, riferimenti o parti della descrizione.

Esempio:

    "AMAZON EU SARL 123456"

NON deve diventare automaticamente:

    "amazon"

perché potrebbe eliminare informazioni necessarie a distinguere due movimenti.

---

# 9. NORMALIZZAZIONE PER BANK PARSER

Ogni BankParser deve poter implementare la propria normalizzazione specifica.

Esempio:

    TradeRepublicParser
        -> Trade Republic normalization

    BancoPostaParser
        -> BancoPosta normalization

La logica specifica della banca NON deve essere sparsa nel Deduplication Engine.

Il Deduplication Engine deve ricevere dati già normalizzati.

Pipeline:

    PDF
      ↓
    BankParser
      ↓
    canonical transaction data
      ↓
    normalization
      ↓
    fingerprint
      ↓
    Deduplication Engine

---

# 10. SALDO TRADE REPUBLIC

Nel PDF Trade Republic è presente una colonna:

    Saldo

che rappresenta il saldo dopo il movimento.

Verificare se Lumio dispone già di un campo equivalente.

Se non esiste e se è coerente con l'architettura, valutare l'introduzione di un campo opzionale come:

    balance_after

Il saldo NON deve essere obbligatoriamente parte del fingerprint principale.

Deve essere considerato informazione secondaria utile per:

- matching;
- disambiguazione;
- visualizzazione nella review;
- validazione del parser.

Non tutti i BankParser potrebbero fornire questo dato.

---

# 11. OCCURRENCE MATCHING

Questo è uno dei requisiti più importanti.

NON fare:

    fingerprint exists → duplicate

Utilizzare invece il numero di occorrenze.

Esempio database:

    fingerprint X = 2 record

Nuovo import:

    fingerprint X = 3 record

Risultato:

    2 duplicate
    1 new

Altro esempio:

Database:

    fingerprint X = 3

Nuovo PDF:

    fingerprint X = 2

Risultato:

    2 duplicate
    0 new

Questo deve funzionare anche quando esistono transazioni perfettamente identiche.

Il matching deve quindi essere basato sul numero di occorrenze già presenti rispetto alle occorrenze del nuovo import.

---

# 12. PERFORMANCE

Il sistema deve essere progettato per:

- uso personale: meno di 10.000 transazioni;
- possibile futuro commerciale: oltre 100.000 transazioni.

NON implementare un confronto O(N×M) in Python.

NON caricare tutte le transazioni esistenti in memoria per confrontarle una alla volta.

Il database deve essere sfruttato tramite:

- indici;
- query aggregate;
- batch query;
- confronti per fingerprint;
- operazioni bulk dove appropriate.

Valutare attentamente gli indici PostgreSQL.

---

# 13. STATI DEL RECORD DURANTE IL DEDUP

Ogni record del nuovo import deve poter assumere concettualmente uno stato:

    NEW
    DUPLICATE
    REVIEW

### NEW

Nessun match affidabile.

→ importabile automaticamente.

### DUPLICATE

Corrispondenza sufficientemente certa.

→ non creare una nuova transaction.

### REVIEW

Il sistema ha trovato una possibile corrispondenza ma non è sufficientemente sicuro.

→ chiedere esplicitamente all'utente cosa fare.

---

# 14. SISTEMA MOLTO CONSERVATIVO

La regola generale deve essere:

    false positive > false negative

NON cancellare o scartare automaticamente una transazione reale sulla base di un matching incerto.

Se il sistema non è sufficientemente sicuro:

    REVIEW

e mai:

    automatic duplicate

---

# 15. REVIEW UI

Implementare una vera esperienza di review.

Quando esistono record ambigui, mostrare all'utente il confronto tra:

    NUOVO RECORD

e

    RECORD GIÀ PRESENTE

Mostrare almeno:

- data;
- descrizione raw;
- descrizione normalizzata, se utile;
- importo;
- currency;
- transaction type;
- saldo, se disponibile;
- account;
- eventuali altri dati rilevanti.

Esempio concettuale:

    POSSIBILE DUPLICATO

    Nuovo movimento
    ------------------------
    Data: 19/08/2026
    Descrizione: AMAZON EU SARL
    Importo: -42,50 EUR
    Tipo: expense
    Saldo: 1.245,32 EUR

    Movimento già presente
    ------------------------
    Data: 19/08/2026
    Descrizione: Amazon EU SARL
    Importo: -42,50 EUR
    Tipo: expense
    Saldo: 1.245,32 EUR

    [IMPORTA COMUNQUE]
    [NON IMPORTARE]

La UI deve essere chiara e non ambigua.

---

# 16. DECISIONE DELL'UTENTE

Quando l'utente sceglie:

    NON IMPORTARE

il record viene scartato dal nuovo import.

Quando l'utente sceglie:

    IMPORTA COMUNQUE

il record viene importato.

MA il fingerprint NON deve essere modificato.

NON creare fingerprint artificiali per aggirare il sistema.

NON alterare la transaction identity.

---

# 17. MEMORIZZAZIONE DELLE DECISIONI MANUALI

Quando l'utente sceglie:

    IMPORTA COMUNQUE

su una coppia ambigua:

    nuovo record X
    record esistente Y

memorizzare la decisione:

    X ≠ Y

in modo persistente.

L'obiettivo è impedire che lo stesso identico caso venga riproposto continuamente durante futuri import.

La decisione deve essere associata alla specifica relazione di matching e NON deve modificare il fingerprint globale.

Progettare una struttura appropriata in base allo schema esistente.

Possibile concetto:

    deduplication_decisions

con informazioni sufficienti a identificare:

- workspace;
- account;
- nuovo fingerprint/record;
- record esistente;
- tipo di decisione;
- utente;
- timestamp.

NON è obbligatorio usare questo nome o schema: scegliere quello coerente con l'architettura esistente.

---

# 18. IMPORT RECORD vs CANONICAL TRANSACTION

Analizzare se l'attuale modello `imports` è sufficiente per distinguere:

    record letto dal documento

da:

    transaction canonica presente nel database

Se necessario, introdurre una struttura intermedia.

L'obiettivo è poter rappresentare:

    Import #1
       ↓
    record A → imported → transaction 123

    Import #2
       ↓
    record A → duplicate → transaction 123

Il secondo import deve sapere che il record era già presente senza creare una seconda transaction.

Questo è importante per auditabilità e debugging.

---

# 19. IMPORT REPORT

Al termine del deduplication stage mostrare un riepilogo chiaro.

Esempio:

    Import completato

    1.842 movimenti analizzati

    1.105 nuovi
      723 già presenti
       14 da verificare

Se esistono record in REVIEW:

    14 movimenti richiedono la tua decisione

Il job deve rimanere in uno stato coerente con il workflow esistente fino a quando le review richieste sono state gestite.

Non dichiarare semplicemente "completed" se esistono decisioni obbligatorie non ancora risolte, salvo che l'architettura esistente richieda esplicitamente uno stato separato.

---

# 20. RELAZIONE CON IL RULES ENGINE

Il deduplication deve avvenire PRIMA della classificazione finale delle nuove transazioni.

Pipeline:

    Parse
      ↓
    Normalize
      ↓
    Deduplicate
      ↓
    User Review
      ↓
    Persist new transactions
      ↓
    Rules Engine
      ↓
    AI (se configurata)

Una transazione riconosciuta come duplicate NON deve essere riclassificata inutilmente.

---

# 21. AI

Il Deduplication Engine NON deve dipendere dall'AI.

L'applicazione deve funzionare perfettamente con:

    AI disabled

Il matching deterministico deve essere il meccanismo principale.

NON usare LLM per decidere automaticamente se due transazioni sono uguali.

Se in futuro verrà aggiunto un sistema AI per assistere la review, deve essere opzionale e non deve poter causare automaticamente la perdita di dati finanziari.

---

# 22. FILE HASH

Mantenere l'attuale `file_hash`.

Il file hash risolve un problema differente:

    stesso file caricato due volte

Il fingerprint delle transazioni risolve:

    file diversi contenenti gli stessi movimenti

I due sistemi devono coesistere.

Esempio:

    file_hash
        ↓
    duplicate file

    transaction fingerprint
        ↓
    duplicate transactions across different files

NON sostituire il file_hash con il fingerprint.

---

# 23. TRANSACTION DATE

Utilizzare:

    transaction_date

come data principale per l'identità della transazione.

Nel parser Trade Republic questa corrisponde alla colonna:

    DATA

Non introdurre una nuova semantica temporale se non necessaria.

Analizzare comunque il modello esistente per verificare se sono presenti:

- transaction_date;
- value_date;
- booking_date;
- date_raw.

Non confondere questi campi.

---

# 24. TRANSACTION TYPE

Il transaction type deve partecipare all'identità.

Per esempio:

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

Un record:

    Amazon -50 expense

non deve essere considerato identico a un record:

    Amazon +50 refund

solo perché descrizione e data coincidono.

---

# 25. MULTI-TENANCY

Il sistema deve mantenere completamente l'isolamento multi-tenant.

Un record del Workspace A non può mai essere utilizzato come possibile duplicate del Workspace B.

Verificare:

- query;
- repository;
- service;
- DB constraints;
- RLS;
- API authorization.

Aggiungere test espliciti:

    Workspace A
        transaction X

    Workspace B
        stesso fingerprint

    risultato:
        NON duplicate
        nessuna relazione cross-tenant

---

# 26. ACCOUNT ISOLATION

Anche due account dello stesso workspace devono rimanere distinti.

Esempio:

    Account A
    19/08 Amazon -42,50

    Account B
    19/08 Amazon -42,50

NON sono automaticamente la stessa transaction.

`account_id` deve essere parte dello scope dell'identità.

---

# 27. TEST OBBLIGATORI

Implementare una suite completa di test.

## Test 1 — stesso file

Import dello stesso identico PDF due volte.

Risultato:

    secondo upload → file duplicate

Nessuna nuova transaction.

---

## Test 2 — PDF sovrapposti

PDF A:

    gennaio → marzo

PDF B:

    febbraio → giugno

Risultato:

    movimenti sovrapposti → duplicate
    movimenti nuovi → NEW

---

## Test 3 — transazioni identiche legittime

Database:

    2 × stesso fingerprint

Nuovo PDF:

    3 × stesso fingerprint

Risultato:

    2 duplicate
    1 NEW

---

## Test 4 — descrizione differente ma normalizzabile

Esempio:

    "AMAZON EU SARL"
    "amazon eu sarl"

Verificare il comportamento del parser.

---

## Test 5 — descrizione leggermente diversa

Verificare che il sistema NON faccia matching aggressivo automatico.

Caso ambiguo:

    REVIEW

---

## Test 6 — account differenti

Stesso:

    data
    descrizione
    importo
    tipo

ma account differenti.

Risultato:

    NON duplicate

---

## Test 7 — workspace differenti

Stesso fingerprint.

Risultato:

    NON duplicate

---

## Test 8 — currency differente

Stessa data, descrizione e amount numerico ma currency differente.

Risultato:

    NON duplicate

---

## Test 9 — transaction type differente

Stessi altri dati ma:

    expense
    refund

Risultato:

    NON duplicate

---

## Test 10 — review

Creare un caso ambiguo.

Verificare che:

    status = REVIEW

e che l'utente possa:

    IMPORTA COMUNQUE

oppure:

    NON IMPORTARE

---

## Test 11 — manual override

L'utente sceglie:

    IMPORTA COMUNQUE

Verificare che:

- la transaction venga importata;
- la decisione venga persistita;
- lo stesso caso non venga nuovamente proposto inutilmente;
- il fingerprint non venga modificato.

---

## Test 12 — saldo

Se `balance_after` viene implementato:

verificare che venga conservato correttamente e possa essere mostrato durante REVIEW.

---

## Test 13 — no AI

Disabilitare completamente AI.

Tutto il sistema di dedup deve funzionare.

---

## Test 14 — grandi volumi

Creare test con almeno:

    10.000 transactions

e verificare che l'algoritmo non esegua un confronto O(N×M) in Python.

Se appropriato, aggiungere un test più grande per verificare l'uso degli indici.

---

# 28. DATABASE

Creare migration Alembic appropriata.

Gli indici devono essere progettati per supportare:

- workspace;
- account;
- fingerprint;
- transaction_date se utile;
- query di matching;
- query di review.

NON creare una UNIQUE constraint sul fingerprint.

Valutare attentamente eventuali indici compositi.

---

# 29. CONCORRENZA

Prestare particolare attenzione a due import simultanei dello stesso account.

Scenario:

    Import A
    Import B

entrambi contengono la stessa transaction.

Il sistema non deve generare duplicati solamente perché i due job sono stati eseguiti contemporaneamente.

Analizzare transazioni PostgreSQL, locking, isolation level o altre strategie appropriate.

NON introdurre una soluzione fragile basata solamente sul controllo applicativo:

    SELECT
    poi
    INSERT

senza considerare race conditions.

---

# 30. IDEMPOTENZA

Il processo di import deve essere idempotente.

Ripetere lo stesso import o un import equivalente non deve generare progressivamente duplicati.

Testare esplicitamente questo comportamento.

---

# 31. API

Implementare o modificare le API necessarie per:

- ottenere il risultato del dedup;
- ottenere i record in REVIEW;
- visualizzare il confronto;
- decidere IMPORTA;
- decidere NON IMPORTARE;
- ottenere il riepilogo dell'import.

Seguire lo stile API già utilizzato nel progetto.

Non creare endpoint duplicati se esistono già meccanismi equivalenti.

---

# 32. UI

Integrare la funzionalità nella UI esistente.

Non creare una pagina graficamente scollegata dal resto di Lumio.

La UX deve essere moderna, chiara e coerente con il design system esistente.

Durante l'import mostrare:

    Analizzati
    Nuovi
    Duplicati
    Da verificare

La review deve essere semplice e comprensibile anche a un utente non tecnico.

---

# 33. AUDIT

Le decisioni dell'utente devono essere auditabili.

Registrare almeno:

- user;
- timestamp;
- import;
- record coinvolti;
- decisione.

Non registrare dati sensibili inutilmente nei log applicativi.

---

# 34. SICUREZZA

Verificare che:

- un utente non possa vedere review di un altro workspace;
- le API applichino authorization;
- RLS rimanga attiva;
- i record di dedup non permettano data leakage;
- i dati finanziari non finiscano nei log;
- le query siano parametrizzate;
- non vengano bypassate le regole multi-tenant.

---

# 35. NON INTRODURRE

Non introdurre in questa implementazione:

- Open Banking;
- provider bancari esterni;
- LLM per il matching;
- fuzzy matching aggressivo;
- machine learning;
- microservizi aggiuntivi;
- nuove code se non necessarie;
- una nuova architettura parallela all'Import Engine esistente.

La soluzione deve rimanere semplice, deterministica e manutenibile.

---

# 36. CRITERI DI ACCETTAZIONE FINALI

L'implementazione sarà considerata corretta quando:

1. lo stesso PDF caricato due volte non genera duplicati;
2. due PDF diversi con periodi sovrapposti non generano duplicati;
3. transazioni perfettamente identiche ma realmente distinte possono coesistere;
4. il matching è scoped per account e workspace;
5. il fingerprint non è UNIQUE;
6. il matching è deterministico;
7. i casi dubbi richiedono una decisione dell'utente;
8. l'utente vede i due record a confronto;
9. "IMPORTA COMUNQUE" viene memorizzato come decisione tra i due record senza modificare il fingerprint;
10. la stessa ambiguità non viene riproposta inutilmente;
11. il sistema non dipende dall'AI;
12. il sistema funziona con AI disabilitata;
13. il sistema è idempotente;
14. il sistema gestisce import concorrenti;
15. non esistono query O(N×M) lato Python;
16. i test multi-tenant sono verdi;
17. i test di integrazione sono verdi;
18. Alembic migration funziona da database pulito;
19. la UI mostra correttamente nuovi/duplicati/review;
20. non vengono introdotti regressioni nell'import esistente.

---

# 37. OUTPUT FINALE RICHIESTO A CODEX

Al termine:

1. riepiloga cosa hai modificato;
2. elenca le migration create;
3. elenca i nuovi/modified model;
4. elenca le API modificate/create;
5. elenca le modifiche UI;
6. descrivi brevemente l'algoritmo finale;
7. descrivi la strategia di gestione delle transazioni identiche;
8. descrivi la gestione delle review;
9. descrivi la gestione delle decisioni manuali;
10. elenca tutti i test aggiunti;
11. esegui lint;
12. esegui unit test;
13. esegui integration test;
14. esegui eventuali frontend test;
15. segnala esplicitamente eventuali test non eseguiti e perché.

NON considerare il lavoro completo se il codice è stato modificato ma i test rilevanti non sono stati eseguiti.

La priorità assoluta è:

    INTEGRITÀ DEI DATI FINANZIARI
    >
    CORRETTEZZA DEL MATCHING
    >
    SICUREZZA MULTI-TENANT
    >
    PERFORMANCE
    >
    COMODITÀ
## Task: progettare e implementare una market-data architecture seria per prezzi daily, intraday e realtime

Voglio rifattorizzare la gestione dei prezzi di mercato dell'applicazione partendo dall'architettura esistente.

### Contesto attuale

L'applicazione ha già una cache/persistenza applicativa dei prezzi:

* `asset_prices` è attualmente la fonte di verità per la valorizzazione.
* La tabella è concepita come **una riga per asset e giorno**, con upsert sulla `price_date`.
* Viene utilizzata per:

  * valorizzazione;
  * snapshot;
  * storico/performance.
* Il codice e la documentazione/commento in `base.py` chiariscono questa semantica.
* Il market-data provider live non deve essere utilizzato direttamente come fonte di verità per la valorizzazione.
* Il job attuale è un cron giornaliero fisso.
* Il job oggi lavora su tutti gli `Asset` che hanno `symbol`/`isin`, anche se non hanno posizioni attive.
* Non esiste attualmente un TTL/refresh interval configurabile per profilo.
* Esiste `MarketDataProfile`, che può essere esteso con una configurazione relativa al refresh.

### Nuovo requisito

Vogliamo supportare correttamente tre concetti distinti:

1. **Prezzo giornaliero canonico**

   * utilizzato per valorizzazione storica, snapshot, performance e storico;
   * stabile e indipendente dal fatto che un utente abbia aperto o meno una pagina.

2. **Dati intraday**

   * utilizzabili per grafici, analisi e funzionalità future;
   * devono avere timestamp;
   * non devono alterare la semantica del prezzo daily canonico.

3. **Latest/live quote**

   * utilizzata dalla UI, soprattutto nella pagina dettaglio del singolo asset;
   * può essere aggiornata frequentemente;
   * può essere effimera;
   * Redis può essere utilizzato come cache con TTL;
   * il provider live non deve diventare accidentalmente la fonte di verità della valorizzazione.

### Principio architetturale desiderato

Voglio una separazione esplicita:

```text
Daily canonical price
    -> database
    -> storico / snapshot / valorizzazione

Intraday market data
    -> time-series storage/database
    -> grafici / analisi

Latest quote
    -> Redis
    -> UI realtime
    -> TTL
```

La regola fondamentale deve essere:

> Redis contiene dati veloci e sacrificabili; il database intraday contiene i dati osservati; il database daily contiene il dato canonico utilizzato per la valorizzazione.

---

## Obiettivo

Analizza prima il repository e proponi una soluzione production-grade coerente con l'architettura esistente.

NON partire immediatamente modificando il codice.

### Fase 1 — analisi

Ispeziona almeno:

* `market_data.py`
* `base.py`
* definizione di `Asset`
* definizione di `MarketDataProfile`
* definizione di `asset_prices`
* codice di valorizzazione
* codice degli snapshot
* job/cron che aggiorna i prezzi
* eventuali API/service usati dalla pagina dettaglio asset
* configurazione Redis, se già presente
* sistema di migration/database
* test esistenti relativi ai market data

Ricostruisci il data flow attuale.

In particolare voglio capire:

```text
provider
   ↓
?
   ↓
asset_prices
   ↓
valuation
   ↓
snapshot/history
```

e:

```text
UI asset detail
   ↓
?
   ↓
provider/cache
```

---

## Fase 2 — proposta architetturale

Prima di implementare, proponi esplicitamente il modello dati.

La soluzione di riferimento che voglio valutare è concettualmente questa:

### `asset_prices_daily`

Prezzo canonico giornaliero.

Possibile struttura:

```text
asset_id
price_date
open
high
low
close
adjusted_close
volume
currency
source
created_at
updated_at
```

con vincolo:

```text
UNIQUE(asset_id, price_date)
```

Ma NON assumere automaticamente questi campi: verifica cosa contiene oggi `asset_prices` e adatta il modello alle necessità reali dell'applicazione.

### Intraday

Valuta se sia meglio:

```text
asset_prices_intraday
```

oppure una struttura time-series più appropriata.

Deve supportare almeno:

```text
asset_id
quoted_at
price
source
```

e, se architetturalmente appropriato:

```text
bid
ask
volume
currency
exchange
```

Valuta anche il concetto di OHLC bars:

```text
asset_price_bars
asset_id
interval
bar_start
open
high
low
close
volume
```

Non introdurre complessità inutilmente: spiega quando servono realmente raw quotes/tick e quando invece è sufficiente una granularità intraday.

---

## Redis

Progetta una cache latest quote per asset.

Esempio concettuale:

```text
market:quote:{asset_id}
```

Payload indicativo:

```json
{
  "price": 183.42,
  "currency": "USD",
  "quoted_at": "2026-08-28T18:57:12Z",
  "source": "provider"
}
```

Il valore deve avere TTL.

Voglio però evitare cache stampede.

Progetta quindi anche un meccanismo di locking/deduplication per evitare che, quando una quote scade, 50 richieste contemporanee provochino 50 richieste al provider.

Valuta una struttura tipo:

```text
market:quote:lock:{asset_id}
```

con comportamento equivalente a:

```text
request 1 -> provider -> Redis
request 2 -> aspetta/riusa
request 3 -> aspetta/riusa
...
```

Non assumere Redis se il progetto non lo utilizza già: verifica prima l'infrastruttura esistente.

---

## Refresh interval

Estendi `MarketDataProfile` con un parametro tipo:

```text
refresh_interval
```

con un default ragionevole, ad esempio 15 minuti.

Il significato deve essere chiaramente definito.

Preferibilmente:

> minimum refresh interval per asset/profilo verso il provider

e non necessariamente "TTL esatto del valore".

Valuta se il TTL Redis debba essere leggermente superiore al refresh interval per evitare race condition allo scadere.

Verifica anche:

* unità di misura;
* validazione;
* valori min/max;
* migration;
* default;
* UI/settings;
* backward compatibility.

---

## Job giornaliero

Modifica il job in modo che non processi inutilmente tutti gli asset con `symbol`/`isin`.

Dovrebbe considerare solo gli asset collegati a **posizioni attive**, se questa è effettivamente la semantica corretta dell'applicazione.

Verifica attentamente come sono modellate:

* Position
* Asset
* portfolio/account
* stato active/closed

Non inventare colonne o relazioni.

Ottimizza la query per evitare N+1.

---

## Regole di business

Implementa/garantisci esplicitamente queste regole:

### Valorizzazione storica

```text
snapshot storico
    ↓
daily canonical price
    ↓
database
```

NON:

```text
snapshot
    ↓
provider live
```

### Valorizzazione realtime

Se l'applicazione ha bisogno di una valorizzazione realtime nella UI:

```text
UI
 ↓
latest quote
 ↓
Redis
 ↓
provider solo se necessario
```

Deve essere evidente nel codice che questa è una valorizzazione realtime/display e non modifica il prezzo storico canonico.

### Daily price

Il prezzo daily non deve diventare:

> "ultimo prezzo visto perché qualcuno ha aperto la pagina".

La visita di una pagina non deve modificare retroattivamente il significato del dato storico.

---

## Provider abstraction

Verifica l'astrazione attuale del provider.

Se appropriato, porta il codice verso una separazione del tipo:

```text
MarketDataProvider
    ├── get_daily_prices(...)
    ├── get_intraday(...)
    └── get_latest_quote(...)
```

oppure una struttura migliore coerente con il repository.

NON creare un'astrazione artificiale se il progetto ne ha già una adeguata.

Il resto dell'applicazione non dovrebbe dipendere direttamente dall'implementazione Yahoo/provider.

---

## Storage decision

Valuta concretamente il database già utilizzato dal progetto.

Non introdurre TimescaleDB o ClickHouse solo per principio.

Voglio una decisione motivata tra:

1. PostgreSQL normale + tabelle/indici/partitioning;
2. PostgreSQL + TimescaleDB;
3. altro storage time-series.

La decisione deve basarsi sul volume realistico del progetto.

Redis deve rimanere una cache e NON il database storico primario.

---

## Retention

Proponi una retention policy per i dati intraday.

Ad esempio, solo come punto di partenza:

```text
raw/high-frequency -> retention limitata
1m bars             -> retention più lunga
5m/15m bars         -> retention ancora più lunga
daily               -> retention indefinita
latest quote        -> Redis TTL
```

Non implementare retention arbitraria senza prima verificare i requisiti e il provider.

Considera anche eventuali vincoli di licenza/uso dei dati del provider.

---

## Concorrenza e consistenza

Analizza questi casi:

### Caso 1

Due utenti aprono contemporaneamente lo stesso asset.

Non devono generare due richieste inutili al provider.

### Caso 2

La cache Redis scade durante una richiesta.

Non deve esserci uno storm di richieste.

### Caso 3

Il provider è down.

La UI deve poter utilizzare eventualmente l'ultima quote disponibile, se compatibile con i requisiti, indicando correttamente che il dato è stale.

Il sistema non deve cancellare il dato storico perché il provider live non risponde.

### Caso 4

Il provider restituisce un timestamp più vecchio di quello già presente.

Non sovrascrivere ingenuamente una quote più recente con una più vecchia.

---

# Fase 3 — migrazione

Progetta una migration sicura.

La migrazione deve:

* preservare i dati esistenti;
* mantenere compatibilità con il codice attuale durante la transizione, se necessario;
* trasferire `asset_prices` verso la nuova struttura daily se questo è il design scelto;
* creare gli indici corretti;
* creare unique constraint;
* evitare downtime non necessario;
* essere idempotente dove appropriato.

Non cancellare la vecchia struttura finché non è chiaro che tutte le dipendenze sono state migrate.

---

# Fase 4 — implementazione

Dopo aver presentato il piano, implementa il cambiamento.

Mantieni lo scope ragionevole.

Non fare refactoring non correlati.

Segui lo stile e le convenzioni già presenti nel repository.

Aggiungi test per almeno:

1. daily price upsert;
2. intraday insert;
3. latest quote Redis;
4. TTL;
5. cache hit;
6. cache miss;
7. concurrent cache miss / lock;
8. provider failure;
9. stale quote;
10. valorizzazione che utilizza il daily canonical price;
11. snapshot che utilizza il daily canonical price;
12. job che seleziona solo le posizioni attive;
13. `refresh_interval` del `MarketDataProfile`;
14. backward compatibility con profili esistenti.

---

# Fase 5 — output finale

Alla fine voglio un report sintetico ma tecnico con:

### Architecture

Schema finale del data flow.

### Database

Tabelle create/modificate, colonne, indici e constraint.

### Redis

Key structure, TTL, locking e comportamento in caso di cache miss.

### API/services

Nuovi o modificati service/metodi.

### Jobs

Come funziona il job giornaliero e come seleziona gli asset.

### Migration

Come vengono migrati i dati esistenti.

### Tests

Quali test sono stati aggiunti.

### Trade-offs

Spiega brevemente le decisioni architetturali principali e perché sono state preferite alle alternative.

---

## Vincoli importanti

1. **Non usare il provider live direttamente per la valorizzazione storica.**
2. **Non trasformare accidentalmente il prezzo daily in "ultimo prezzo visto dalla UI".**
3. **Redis è cache, non source of truth storico.**
4. **Non introdurre un database time-series pesante senza motivazione basata sui volumi reali.**
5. **Non fare N+1 query nel job.**
6. **Non fare N richieste al provider quando N utenti chiedono contemporaneamente lo stesso asset.**
7. **Non inventare relazioni/modelli: prima ispeziona il repository.**
8. **Prima analizza e proponi il design; poi implementa.**
9. **Mantieni backward compatibility dove ragionevolmente possibile.**
10. **Non fare modifiche non correlate al problema.**

Prima di scrivere codice, mostrami:

1. l'architettura attuale che hai ricostruito;
2. i problemi che hai trovato;
3. il modello dati proposto;
4. il data flow Redis/provider/database;
5. la strategia di migrazione;
6. i principali trade-off.

Dopo questa analisi puoi procedere con l'implementazione.

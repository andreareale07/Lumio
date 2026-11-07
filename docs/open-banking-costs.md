# Open Banking: costi e condizioni dei provider

Verificato il **2026-11-06**. Le condizioni dei provider cambiano: prima di
affidarti a questo documento rileggi le fonti. Dove un dato non è stato trovato
in una fonte ufficiale è marcato **NON CONFERMATO**.

## Risposta breve

**Esiste una sola strada gratuita e legalmente utilizzabile: ogni persona usa
la _propria_ applicazione Enable Banking in "modalità ristretta", solo per i
propri conti personali.** Non esiste una soluzione gratuita per un servizio
condiviso o centralizzato, né per conti aziendali. Lumio è costruito su questo
modello: nessuna credenziale è inclusa nel codice, nessun servizio centrale.

Il "gratis" è una condizione contrattuale del provider, non una proprietà del
software: i Terms di Enable Banking prevedono che possano cambiare. Per questo
l'integrazione è **opzionale** e l'import da PDF/CSV resta sempre disponibile.

## Classifica (dalla più conveniente)

| # | Soluzione | Costo iniziale | Costo mensile | Costo per conto | Utilizzabile da utenti indipendenti che installano Lumio? |
|---|---|---|---|---|---|
| 1 | **Import PDF/CSV** (già in Lumio) | 0 | 0 | 0 | Sì, sempre |
| 2 | **Enable Banking, modalità ristretta** | 0 | 0 | 0 | **Sì, solo uso personale** con conti propri (vedi sotto) |
| 3 | GoCardless Bank Account Data | — | — | — | **No**: dal luglio 2025 non accetta nuove iscrizioni (documentazione di Actual Budget; nessun annuncio ufficiale trovato). Chi ha un account esistente può continuare |
| 4 | Yapily, Tink, Salt Edge | su preventivo | su preventivo | su preventivo | No (contratto commerciale; solo sandbox gratuita) |
| 5 | Accesso diretto PSD2 alle banche | certificato eIDAS (QSeal) + autorizzazione AISP | costi di compliance | — | No: richiede di essere un prestatore autorizzato. Per Trade Republic, ad esempio, la guida TPP richiede un certificato QSeal |

## Enable Banking: cosa dicono i Terms (aggiornati il 2026-01-09)

Fonte: <https://enablebanking.com/terms/> e
<https://enablebanking.com/docs/api/linked-accounts/>

| Punto | Condizione |
|---|---|
| Costo | "Use of the Control Panel and the API under these Terms is free of charge." Un uso fuori dai Terms richiede un accordo separato con prezzi propri (FAQ: prezzi a volume con minimo mensile, importo NON CONFERMATO) |
| Chi può usarlo gratis | Produzione "limited to Linked Accounts" e "solely for evaluation purposes or for the personal use of private individuals" |
| Quanti conti | "The number of Linked Accounts per Application may be limited" (limite NON CONFERMATO) |
| Conti aziendali, scopi commerciali | Esclusi ("any business or professional purpose") |
| Conti di altre persone | Vietato accedere a conti che non appartengono all'utente del Control Panel che li ha collegati |
| Redistribuzione | Vietato concedere o rendere accessibile l'API a terzi; la FAQ aggiunge che le applicazioni non possono essere rese pubbliche prima di un contratto |
| Autorizzazione AISP | Non serve all'utente: il provider agisce come AISP autorizzato (registro EBA, FIN-FSA) |
| Responsabilità | Limitata a 100 € per il provider; illimitata per chi viola i Terms |
| Modifiche | Il provider può modificare o interrompere le funzioni; "No fees will be applied retroactively without prior notice" |

### Cosa implica per Lumio

* **Credenziali per utente.** Ogni persona registra la propria applicazione e
  carica il certificato generato da Lumio (la chiave privata resta sul server).
  Due membri dello stesso workspace non condividono credenziali né conti
  collegati: lo garantisce la RLS (owner-only), non solo la UI.
* **Nessuna credenziale condivisa** nel repository, in `.env.example` o in
  un'immagine Docker.
* **Un servizio gestito per terzi** (un'istanza tua usata da altri) richiederebbe
  un accordo a pagamento con il provider: non è coperto da questo documento.
* **Conti aziendali**: usa l'import da PDF/CSV.

## Limiti operativi (utili per capire cosa aspettarsi)

| Aspetto | Valore | Fonte |
|---|---|---|
| Durata del consenso | Dipende dalla banca, di norma fino a 180 giorni (`maximum_consent_validity`); poi si rinnova con una nuova autorizzazione | FAQ e API reference |
| Letture in background | Molte banche limitano a circa 4 al giorno senza l'utente presente; con l'utente presente (sync manuale) il limite non si applica | FAQ |
| Storico | Di norma almeno un anno; molte banche limitano a 90 giorni dopo la prima ora dal consenso (poi serve una seconda autenticazione forte per le banche che lo richiedono) | FAQ, pagina Italia |
| Un solo consenso attivo | Molte banche italiane ammettono un consenso per applicazione e utente: un nuovo consenso invalida il precedente | Pagina Italia |
| Movimenti in sospeso | Non importati da Lumio (nessun id stabile garantito): solo movimenti contabilizzati | Scelta di progetto |

## Altri provider valutati

* **GoCardless Bank Account Data (ex Nordigen)**: era gratuito (limiti a 4
  sincronizzazioni al giorno per banca), ma le nuove iscrizioni sono chiuse dal
  luglio 2025. Non utilizzabile per nuovi utenti.
* **Tink, Salt Edge, Yapily**: prezzi su preventivo, nessun piano gratuito di
  produzione trovato (Yapily: sandbox gratuita). Fonti secondarie: da verificare
  direttamente.

## Fonti

* Terms of Service Enable Banking — <https://enablebanking.com/terms/>
* Linked accounts / restricted mode — <https://enablebanking.com/docs/api/linked-accounts/>
* FAQ Enable Banking — <https://enablebanking.com/docs/faq/>
* API reference — <https://enablebanking.com/docs/api/reference/>
* Mercato italiano — <https://enablebanking.com/docs/markets/it/>
* GoCardless e alternative — <https://actualbudget.org/docs/advanced/bank-sync/gocardless/>,
  <https://openbankingtracker.com/guides/free-open-banking-apis> (fonti secondarie)
* Trade Republic, guida TPP — <https://assets.traderepublic.com/assets/files/TPP_API_Guide_v2.pdf>

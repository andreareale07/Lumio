# Open Banking: configurazione e messa in produzione

Guida passo passo per attivare l'importazione automatica dei movimenti con
[Enable Banking](https://enablebanking.com). L'integrazione è **opzionale**:
senza, Lumio funziona al 100% con l'import da PDF e CSV.

Prima di cominciare leggi [costi e condizioni](open-banking-costs.md): il
servizio è gratuito **solo per uso personale con conti intestati a te**, e ogni
persona usa la propria applicazione.

## Come funziona

```
Lumio (il tuo server) ──API firmata con la TUA chiave──> Enable Banking ──> la tua banca
        ^                                                       |
        └──────── il browser torna su Lumio dopo il login ──────┘
```

* Lumio legge solo conti, saldi e movimenti (sola lettura). Non può disporre pagamenti.
* Le credenziali bancarie si inseriscono **solo sul sito o nell'app della banca**.
* I movimenti arrivano a Lumio passando da Enable Banking e restano sul tuo server.
* La chiave privata è generata da Lumio, cifrata a riposo, e non esce mai dal server.
  Al provider si carica solo il certificato pubblico.

## Requisiti

* Lumio raggiungibile in **HTTPS** da un dominio (anche DuckDNS). La banca
  riporta il tuo browser sull'indirizzo di ritorno: deve funzionare dal browser
  con cui fai il collegamento. Il provider non deve raggiungere il tuo server.
* Un account gratuito sul Control Panel di Enable Banking.
* Conti **personali** intestati a te.

## Messa in produzione (aggiornamento di un'istanza esistente)

> La migration `0044` è additiva (tre tabelle nuove, una colonna in
> `transactions`, estensione di due vincoli) ma modifica il database: fai prima
> un backup.

1. **Backup del database.** Esempio con Postgres nel compose
   (adatta nomi e utente alla tua installazione, vedi [`DEPLOY_PROXMOX.md`](DEPLOY_PROXMOX.md)):

   ```bash
   docker compose exec -T postgres pg_dump -U <utente_admin> -d lumio -Fc > lumio-prima-open-banking.dump
   ```

   Conserva anche il valore di `SECRET_KEY` del tuo `.env`: le chiavi bancarie
   sono cifrate con una chiave derivata da quel valore. Se lo cambi in futuro,
   dovrai rigenerare le credenziali Open Banking.

2. **Aggiorna il codice** (`git pull`) nella cartella in cui gira Lumio.

3. **Imposta il `.env`** (variabili in `.env.example`):

   ```ini
   OPEN_BANKING_ENABLED=true
   OPEN_BANKING_REDIRECT_URI=https://<il-tuo-dominio>/api/v1/open-banking/callback
   ```

   L'indirizzo deve essere lo stesso dominio HTTPS da cui usi Lumio. Ti servirà
   identico nel passo 2 della configurazione guidata.

4. **Ricostruisci e riavvia** (le migration si applicano da sole all'avvio di `app`).
   Con i file di produzione del tuo deploy, ad esempio:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.prod.local-db.yml up -d --build
   docker compose restart frontend
   ```

5. **Verifica.**

   ```bash
   docker compose logs app | grep -i "0044_open_banking"   # migration applicata
   curl -s https://<il-tuo-dominio>/api/v1/health
   ```

   In Lumio devi vedere la voce **Impostazioni > Conti bancari collegati**.
   Se non compare, ricontrolla `OPEN_BANKING_ENABLED` e riavvia `app`: il router
   si monta una sola volta all'avvio.

## Configurazione guidata (una volta, per ogni persona)

In **Impostazioni > Conti bancari collegati** Lumio ti guida in tre passi:

1. **Genera il certificato.** Scaricalo o copialo.
2. **Registra la tua applicazione** sul Control Panel di Enable Banking
   (<https://enablebanking.com/cp>):
   * crea un account gratuito;
   * registra una nuova applicazione scegliendo l'ambiente **Production**;
   * carica il certificato del passo 1 e annota l'**Application ID**;
   * come **Redirect URL** inserisci esattamente l'indirizzo mostrato da Lumio;
   * attiva l'applicazione in **modalità ristretta** collegando dal Control
     Panel almeno uno dei tuoi conti (questo è il requisito per l'uso gratuito).
3. **Incolla l'Application ID** in Lumio e salva.

## Collegare una banca

1. **Collega una banca**, scegli il paese e cerca il nome.
2. Leggi il riepilogo e tocca **Vai alla banca**: ti autentichi sul sito o
   nell'app della banca (per Poste Italiane con PosteID) e autorizzi la lettura.
3. Tornato in Lumio, per ogni conto scegli **Importa questo conto** e abbinalo a
   un conto Lumio nuovo o esistente. Nessun abbinamento è automatico.
4. Tocca **Sincronizza ora**. La prima volta Lumio chiede lo storico più lungo
   che la banca consente. Poi la sincronizzazione è automatica.

Sincronizzazione automatica: ogni connessione si aggiorna al massimo ogni
`OPEN_BANKING_SYNC_INTERVAL_HOURS` ore (default 8, minimo 6). Dopo un errore
temporaneo Lumio ritenta con attesa crescente; se la banca limita le richieste
l'attesa è più lunga. A ogni sincronizzazione vengono riletti gli ultimi
`OPEN_BANKING_RECONCILE_DAYS` giorni (default 7) e i movimenti già presenti non
vengono duplicati (identificativo della banca, poi controllo a impronta come per
i file). I casi ambigui finiscono in "da rivedere", come negli import.

Il consenso dura al massimo 180 giorni (meno per alcune banche). Prima della
scadenza compare un avviso in tutta l'app; **Rinnova autorizzazione** ripete il
login mantenendo abbinamenti e storico.

## Cosa non fa

* Non importa i movimenti **in sospeso** (nessun identificativo stabile): solo i contabilizzati.
* Non funziona con conti aziendali sul piano gratuito.
* Trade Republic: usa l'import da PDF (vedi [copertura](open-banking-coverage.md)).
* Se cancelli un import "Open Banking" dalla pagina Import, la sincronizzazione
  riparte dall'ultimo movimento importato: non rilegge lo storico cancellato.

## Rollback e disattivazione

* **Disattivare**: `OPEN_BANKING_ENABLED=false` e riavvio di `app` e `worker`. La
  voce di menu e gli endpoint spariscono; i dati importati restano.
* **Scollegare una banca**: dalla pagina; Lumio revoca il consenso presso la banca.
* **Eliminare le credenziali**: revoca tutte le banche e cancella chiavi e
  collegamenti. I movimenti importati restano.
* **Tornare alla versione precedente del database** (solo se necessario):
  ripristina il backup oppure `alembic downgrade -1` (le righe "open_banking"
  degli import diventano "csv", le transazioni restano).

## Sicurezza e privacy

* Segreti cifrati a riposo (Fernet, chiave derivata da `SECRET_KEY` con una
  derivazione dedicata alla cifratura), mai nei log, nelle risposte API o nel
  browser. Nessuna credenziale nel repository. **`SECRET_KEY` deve essere un
  valore casuale lungo almeno 32 caratteri**: con `APP_ENV=production` l'app non
  parte con un valore breve o con quello di esempio. Se lo cambi, rigenera le
  credenziali Open Banking.
* L'indirizzo che la banca ti propone di aprire è accettato solo se è `https`;
  i loghi delle banche solo se `https` e vengono caricati senza inviare il tuo
  dominio come referrer (il sito che li ospita vede comunque il tuo indirizzo IP).
* Il `code` e lo `state` del callback non finiscono nei log di accesso di nginx
  e di uvicorn. Restano nel log di *errore* di nginx se in quel momento il
  backend non risponde.
* Lo scollegamento con "elimina anche i movimenti" è rifiutato (409) mentre una
  sincronizzazione è in corso: riprova dopo qualche secondo.
* La sincronizzazione manuale ha una pausa minima di 30 secondi.
* Se metti Lumio dietro un reverse proxy con indirizzo **pubblico**, aggiungilo a
  `set_real_ip_from` in `frontend/nginx.conf`: serve all'IP reale che Lumio
  dichiara alla banca e ai limiti di richieste.
* Credenziali e connessioni visibili solo al loro proprietario (RLS a livello di
  database): nemmeno gli altri membri dello stesso workspace le vedono.
* Il callback è l'unico endpoint non autenticato: accetta solo uno `state`
  firmato, valido 10 minuti e **monouso**, con limite di richieste.
* **Backup**: include le chiavi cifrate, gli IBAN e i movimenti in chiaro.
  Proteggi i dump come proteggi il `.env` e valuta la cifratura del disco o dei dump.
* **Cancellazione dei dati bancari**: scollega la banca e, se vuoi, elimina gli
  import "Open Banking" dalla pagina Import (cancella i movimenti collegati).
* **Normativa**: Enable Banking opera come prestatore di servizi di informazione
  sui conti autorizzato (PSD2, registro EBA) e raccoglie il tuo consenso con i
  [propri termini per l'utente finale](https://tilisy.enablebanking.com/terms).
  Usando Lumio solo per i tuoi conti, il trattamento dei tuoi dati personali è
  una tua attività personale; se lo mettessi a disposizione di altre persone,
  valuta gli obblighi GDPR e i Terms del provider (vedi
  [costi](open-banking-costs.md)). Questo documento non è consulenza legale.

## Risoluzione dei problemi

| Sintomo | Causa probabile | Cosa fare |
|---|---|---|
| "Indirizzo di ritorno non configurato" | `OPEN_BANKING_REDIRECT_URI` vuoto | Impostalo nel `.env` e riavvia `app` |
| La banca dice che l'URL di ritorno non è valido | Redirect URL diverso da quello registrato | Deve coincidere esattamente (schema, dominio, percorso) |
| "Enable Banking ha rifiutato le credenziali" | Application ID o certificato sbagliati | Ricontrolla l'ID e che il certificato caricato sia quello di Lumio |
| Elenco banche vuoto | Applicazione non ancora attiva | Attivala in modalità ristretta dal Control Panel |
| "La banca ha limitato le richieste" | Limite di letture in background | Aspetta: Lumio riprova da solo; "Sincronizza ora" non ha questo limite |
| "L'autorizzazione è scaduta" | Consenso oltre i 180 giorni | **Rinnova autorizzazione** |
| "La chiave salvata non è più leggibile" | `SECRET_KEY` cambiato | Elimina le credenziali e generale di nuovo |
| Login in Lumio impossibile dopo l'aggiornamento | Cookie `Secure` senza HTTPS | Usa HTTPS (vedi [`DEPLOY_PROXMOX.md`](DEPLOY_PROXMOX.md)) |

## Sviluppo e test

I test automatici usano solo risposte simulate e dati sintetici: nessun conto o
credenziale reale. Il router va attivato **prima** dell'import dell'app:

```bash
cd backend
OPEN_BANKING_ENABLED=true OPEN_BANKING_REDIRECT_URI=https://lumio.example/api/v1/open-banking/callback \
  pytest tests/test_open_banking_api.py tests/test_open_banking_connector.py \
         tests/test_open_banking_state_keys.py tests/test_rls_open_banking.py
```

Come sempre, pytest solo su Postgres e Redis **effimeri** (vedi
`.claude/memoria/guida-metodo-sviluppo-e-test.md`), mai sul database `lumio`.

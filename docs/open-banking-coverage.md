# Open Banking: banche e prodotti supportati

Verificato il **2026-11-06** sulla documentazione ufficiale di Enable Banking
(<https://enablebanking.com/docs/markets/it/>). Questo elenco **non è** una
garanzia di funzionamento: distingue ciò che è dichiarato dal provider da ciò
che è stato provato con conti reali.

## Come leggere le colonne

| Livello | Significato |
|---|---|
| **Dichiarata dal provider** | La documentazione ufficiale cita la banca. Nessuna prova con un conto reale in questo repository |
| **Verificata con test reali** | Un collegamento reale ha funzionato (data e prodotto indicati). Oggi: _nessuna_ |
| **NON CONFERMATO** | Non trovata nelle fonti consultate. Non significa che non sia supportata |

I test automatici di Lumio usano sempre risposte simulate e dati sintetici:
non provano nessuna banca reale.

## Italia

| Istituto | Stato | Autenticazione (da documentazione) | Note e limiti dichiarati |
|---|---|---|---|
| Poste Italiane — **BancoPosta** | Dichiarata dal provider | Redirect, CBI Globe, SCA con **PosteID** | Seconda autenticazione forte per lo storico oltre 90 giorni |
| Poste Italiane — **Postepay** | Dichiarata dal provider (novità del changelog di marzo 2026) | Redirect, CBI Globe, SCA con PosteID; flusso diverso per carta con IBAN e carta prepagata nominativa | Prima di avviare il collegamento il provider chiede di scegliere tra BancoPosta e Postepay |
| Intesa Sanpaolo | Dichiarata dal provider | Redirect, app "Intesa Sanpaolo Mobile" (app switch non automatico) | Seconda SCA per storico oltre 90 giorni |
| UniCredit | Dichiarata dal provider | Redirect, codice utente + PIN, poi OTP SMS o notifica app | Carte di credito non supportate; prepagate solo con IBAN |
| Banco BPM | Dichiarata dal provider | Redirect | Seconda SCA per storico oltre 90 giorni |
| BPER Banca | Dichiarata dal provider | Redirect | Seconda SCA per storico oltre 90 giorni |
| Crédit Agricole Italia (Cariparma) | Dichiarata dal provider | Redirect | Seconda SCA per storico oltre 90 giorni |
| Banca Monte dei Paschi di Siena | Dichiarata dal provider | Redirect | Seconda SCA per storico oltre 90 giorni |
| Fideuram | Dichiarata dal provider | Redirect | Seconda SCA per storico oltre 90 giorni |
| Mediobanca Premier | Dichiarata dal provider | Redirect | Solo conti business: **non utilizzabile** con il piano gratuito (solo uso personale) |
| Gruppo BCC Iccrea, BBVA | Citate nella documentazione | — | Dettagli non verificati |
| Fineco, Banca Mediolanum, ING, Banca Sella, Credem, Widiba | **NON CONFERMATO** | — | Non citate nella pagina Italia. Controlla l'elenco reale dalla tua applicazione |
| Revolut, N26 | **NON CONFERMATO** | — | Non citate nella pagina Italia |
| Trade Republic | **NON CONFERMATO** | — | Vedi sotto |

Ogni istituto ha anche limiti propri per tipo di conto (conto corrente,
risparmio, carte con IBAN, prepagate): la documentazione non li elenca in modo
uniforme, quindi **non assumere** che una banca supporti tutti i suoi prodotti.
Dopo il collegamento Lumio mostra solo i conti che la banca condivide davvero.

### Trade Republic

Trade Republic pubblica una guida PSD2 per _Third-Party Provider_ autorizzati
(richiede un certificato QSeal eIDAS e un'autorizzazione AISP). Che un
aggregatore come Enable Banking la renda accessibile **non è confermato**. Anche
in caso positivo, un'API PSD2 espone movimenti di conto, non le operazioni di
investimento (acquisti, dividendi) con il dettaglio che serve a Lumio. Per
questo **Trade Republic resta un connettore di importazione manuale** (estratto
conto PDF, già supportato). Lumio non usa né userà scraping o l'inserimento
automatico di password e OTP.

## Altri paesi SEE

Il catalogo cambia nel tempo e dipende da quanto offre il provider. Lumio
ottiene l'elenco **dinamicamente** dall'API (`GET /aspsps`) quando scegli il
paese in "Collega una banca": non c'è un elenco statico da mantenere. Paesi
selezionabili nell'interfaccia: Italia, Austria, Belgio, Bulgaria, Croazia,
Cipro, Cechia, Danimarca, Estonia, Finlandia, Francia, Germania, Grecia,
Ungheria, Islanda, Irlanda, Lettonia, Liechtenstein, Lituania, Lussemburgo,
Malta, Paesi Bassi, Norvegia, Polonia, Portogallo, Romania, Slovacchia,
Slovenia, Spagna, Svezia. La presenza di un paese nell'elenco non implica che il
provider copra ogni sua banca.

## Aggiornare questo elenco

Con le tue credenziali (application ID e chiave) puoi produrre l'elenco reale
del provider per i paesi che ti interessano:

```bash
cd backend
python scripts/gen_openbanking_coverage.py \
  --application-id <ID> --private-key-file chiave.pem --countries IT,DE,FR > catalogo.md
```

Lo script elenca solo cosa il provider **ha a catalogo** (livello "dichiarata
dal provider"): saldi, storico e tipi di conto vanno verificati con un
collegamento reale. Quando ne provi uno, annota qui la data e il prodotto
verificato (livello "verificata con test reali").

| Istituto | Prodotto | Data | Esito |
|---|---|---|---|
| _nessuno ancora_ | | | |

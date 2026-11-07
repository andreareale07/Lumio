# Prompt per riprendere lo sviluppo Open Banking (nuova sessione)

Incolla il testo qui sotto come primo messaggio di una nuova sessione nella cartella del progetto.

---

Riprendiamo lo sviluppo dell'integrazione **Open Banking (Enable Banking)** di Lumio, sviluppata il 2026-11-06 e **non ancora committata**.
Prima di scrivere codice nuovo voglio **un'analisi di sicurezza completa** di quanto già fatto.

## Contesto (leggi senza che te lo chieda)
1. `CLAUDE.md` e le schede in `.claude/memoria/`: `task-open-banking.md` (stato, scelte, insidie, punti di sicurezza già noti),
   `progetto-backend.md`, `progetto-database-rls.md`, `guida-metodo-sviluppo-e-test.md`, `guida-import-e-movimenti.md`.
2. `docs/open-banking-setup.md`, `docs/open-banking-costs.md` (vincolo dei Terms: uso personale, credenziali per utente, mai condivise).
3. Il codice: `backend/app/openbanking/`, `backend/app/api/v1/open_banking.py`, `backend/app/services/{open_banking_service,bank_sync_service,import_deletion}.py`,
   `backend/app/worker/jobs/bank_sync_job.py`, `backend/alembic/versions/0044_open_banking.py`, `backend/app/core/{crypto,security,rate_limit}.py`,
   `frontend/src/features/settings/open-banking/`, `frontend/nginx.conf`, i file `docker-compose*.yml` e `.env.example`.
   Usa `git status` e `git diff` per vedere tutto ciò che non è committato.

## Fase 1: analisi di sicurezza (solo lettura e prove, nessuna modifica al codice)
Fai un threat model (asset: chiave privata RSA, application ID, session ID bancari, movimenti; attori: utente malintenzionato dello stesso workspace,
utente di un altro workspace, attaccante di rete, chi ha il solo dump del DB, chi ha il solo `.env`, provider compromesso) e verifica, con prove dove possibile:

- **Callback** (unico endpoint non autenticato): validità e monouso dello `state`, nonce, scadenza, rigiocabilità, CSRF/login CSRF, open redirect,
  rate limit, gestione degli errori senza fughe. Lo `state` è firmato con la stessa `SECRET_KEY` dei JWT di accesso: verifica che un `state`
  non possa mai essere accettato come access token e viceversa (claim `purpose`, algoritmi, `decode_access_token`).
- **Segreti**: chiave Fernet derivata da `SECRET_KEY` (nessuna versione/rotazione, stesso segreto per JWT e cifratura), chiavi in memoria, nei log,
  nei messaggi d'errore, nelle risposte API, in Redis (argomenti dei job), nei backup. `code`/`state` nei log di accesso di uvicorn e nginx.
- **Isolamento**: RLS owner-only (4 comandi per tabella con righe reali), IDOR su `connection_id`/`account_id`/`financial_account_id`,
  funzione `SECURITY DEFINER list_active_bank_connections()` e GRANT, cron senza identità, rischio di leggere/eliminare dati di altri.
- **Input e superficie esterna**: validazione di `application_id`, paese, nome banca; `institutions` senza rate limit che chiama un'API esterna;
  `OPEN_BANKING_BASE_URL` (SSRF solo da configurazione?); `X-Forwarded-For` usato come IP dell'utente (spoofabile) e inoltrato alla banca;
  loghi del provider caricati dal browser (IP/referrer, CSP `img-src`, intestazioni di sicurezza).
- **Eliminazione dei dati** (`delete_data=true`): confini (mai PDF/CSV/manuali), race con sync/import in corso, atomicità, audit log.
- **Sincronizzazione**: lock e backoff su Redis (Redis senza autenticazione nei compose di sviluppo), idempotenza, retry, DoS della banca/provider, gestione dei
  token scaduti e dei consensi revocati, cosa resta dopo la revoca.
- **Privacy/GDPR e PSD2**: minimizzazione (cosa si salva del payload), retention, cancellazione, trasferimento verso Enable Banking, ruolo di Lumio per uso
  personale vs. messa a disposizione di terzi, rispetto dei Terms (credenziali per utente, conti non aziendali).
- **Frontend**: nessun token/segreto nel browser o in `localStorage`, gestione del certificato scaricato (solo parte pubblica), `window.location.assign`
  verso URL del provider (validazione dell'URL), messaggi di errore.
- **Dipendenze e configurazione**: versioni di `pyjwt`, `cryptography`, `httpx`; default sicuri di `.env.example`; `APP_ENV=production` e cookie `Secure`.

Esegui i test solo su Postgres e Redis **effimeri** (mai sul DB `lumio`); per provare il flusso nel browser usa `backend/scripts/mock_enable_banking.py`
(istruzioni nell'intestazione del file). Non leggere né stampare `.env`. Solo dati sintetici.

**Output atteso:** un report con i risultati ordinati per gravità (critico, alto, medio, basso, informativo), per ognuno: dove, scenario d'attacco concreto,
prova, correzione proposta e impatto sul resto del codice. Distingui ciò che è confermato da ciò che è solo sospetto. Pubblicalo come artifact privato
oltre che nel terminale. **Fermati lì e aspetta il mio ok** prima di correggere qualcosa.

## Fase 2 (dopo il mio ok sul report)
Implementa le correzioni approvate con test che le dimostrino (un test che fallisce prima e passa dopo, quando possibile), poi riprendi i residui noti:
commit (solo su mia richiesta), E2E Playwright dedicati, notifiche fuori dall'app, gestione dei movimenti in sospeso, "rileggi lo storico" dopo l'eliminazione
di un import Open Banking, verifica con un conto reale (Poste) insieme a me.

## Regole di lavoro
Lingua: italiano. Commit solo su mia richiesta, mai `Co-Authored-By`, mai push. Per qualsiasi modifica alla UI: prima mockup a confronto e la mia scelta. Mobile first
(375px). Aggiorna la scheda `task-open-banking.md` e dimmi cosa hai aggiornato. La migration `0044` non va applicata al DB reale senza avvisarmi.

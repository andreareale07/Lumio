# Guida: job asincroni (arq + Redis + SSE)

Regola CLAUDE.md: le operazioni lunghe (parsing, AI, export, ricalcoli) si eseguono in un
job sul worker, mai dentro la request. Eccezione accettata: rimappature sincrone su dati di
scala personale (es. rimappatura dei tipi di transazione).

## Pezzi
- Accodamento: `app/worker/queue.py` (`enqueue_*`). Esecuzione: `app/worker/jobs/*.py`,
  registrati in `app/worker/main.py`. Catalogo descrittivo: `app/services/job_registry.py`
  (contato anche da `test_jobs_endpoint.py`: aggiornarlo quando si aggiunge un job).
- Stato persistente: tabella `job_runs` (una riga per workspace e `job_kind`, sovrascritta
  a ogni esecuzione; `JOB_KINDS` e' l'elenco chiuso). `job_run_tracker.tracked_job_run` scrive
  running -> success/failed/cancelled usando **una propria `rls_session`**, mai quella del
  job (un commit intermedio farebbe scadere l'identita' RLS).
- Progresso in tempo reale: `app/services/job_events.py` (Redis + SSE), con `namespace` e
  `topic_id` generici (`import`, `google_export`, ...).
- Interruzione: cooperativa, tramite un segnale su Redis (`job_cancellation.py`, scade dopo
  10 minuti, azzerato all'inizio e alla fine del job). Il job lo controlla tra un blocco e
  l'altro; un job ancora in coda si annulla subito. Stato `cancelled` distinto da `failed`.
- Frontend: `JobRunStatus`, `ActivityIndicator`, pagina `/activity`.

## Regola senza eccezioni: niente `_job_id` fisso per i job rilanciabili
arq considera "gia' esistente" un `_job_id` anche quando in Redis resta solo il
**risultato** di un'esecuzione conclusa (`keep_result`, 1 ora). Con un id fisso per
workspace il secondo clic restituisce 202 ma non fa nulla per un'ora. L'errore si e'
ripetuto 2 volte (market data, poi export Google, "ragionando per analogia").
- Job lanciati da un clic: **nessun `_job_id`**. Per evitare il doppio accodamento si
  controlla `job_runs.status == 'running'` nel router, prima di accodare.
- Ammesso solo con un id naturale mai riusato (es. `import:{import_id}`).

## Altre regole
- I cron che ciclano sui workspace hanno un try/except **per workspace**: un errore su uno
  non deve bloccare gli altri.
- In un job con `rls_session`: un solo commit, alla fine.
- Lo stato "mai eseguito" e' `null` (valido), non un errore.

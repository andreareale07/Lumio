# Guida: Docker Compose e deploy

Riferimento completo: `docs/DEPLOY_PROXMOX.md` e `README.md`. Qui solo cio' che serve
operativamente.

## Profili compose
- Sviluppo: `docker-compose.yml` (postgres, redis, app, worker, frontend). Pubblica 5432 e
  6379 sull'host (comodo in locale, da chiudere in produzione: Redis non ha autenticazione).
- Postgres esterno: `docker-compose.external-db.yml` (ruoli da creare a mano, SQL
  nell'intestazione del file).
- Produzione: aggiungere `docker-compose.prod.yml` (+ `docker-compose.prod.local-db.yml`
  se Postgres e' nel compose). Richiede Compose >= 2.24, frontend su 127.0.0.1 dietro un
  reverse proxy.
- Con `APP_ENV=production` il cookie di refresh e' `Secure`: **senza HTTPS il login non
  funziona**.

## Istanza locale dell'utente
- Container `lumio-app-1`, `lumio-worker-1`, `lumio-frontend-1` (:5173), `lumio-postgres-1`
  (:5432, DB `lumio` con **dati reali**), `lumio-redis-1`.
- Ricostruire e riavviare e' consentito. **Vietato** cancellare dati o volumi, usare
  `down -v`, lanciarci pytest o fare scritture sull'account reale.
- La migration si applica da sola all'avvio di `app` (`alembic upgrade head`): un rebuild
  con una migration nuova modifica davvero il DB reale, quindi va segnalato.
- Ordine dopo una modifica: `docker compose build app worker frontend` -> `up -d` ->
  `restart frontend` se `app` e' stato ricreato (vedi `guida-metodo-sviluppo-e-test.md`).
- Accesso diretto al DB in sola lettura per la diagnostica: `docker exec lumio-postgres-1
  psql -U <superuser> -d lumio` (aggira la RLS: solo SELECT).

## Configurazione
- Tutte le variabili sono in `.env.example`. **`.env` non si legge e non si stampa.**
  `DATABASE_URL` deve usare `lumio_app`, mai il superuser.
- Branding: `APP_NAME`/`APP_TAGLINE` piu' i gemelli `VITE_*` (build arg del frontend: per
  cambiarli serve ricostruire `frontend`).

## Produzione
Nessun accesso a istanze di produzione. Il deploy Proxmox lo fa l'utente seguendo
`docs/DEPLOY_PROXMOX.md`.

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
- Il prod lega il frontend a `127.0.0.1`: con reverse proxy su un altro host/LXC serve
  `FRONTEND_BIND=0.0.0.0` nel `.env` (dal 2026-11-06), altrimenti il proxy dà "Bad Gateway"
  (le richieste non arrivano ai container: log vuoti).
- Con `APP_ENV=production` il cookie di refresh e' `Secure`: **senza HTTPS il login non
  funziona**. Dal 2026-11-07 con `APP_ENV=production` l'app **rifiuta di avviarsi** se
  `SECRET_KEY` ha meno di 32 caratteri o contiene il valore di esempio (`core/config.py`), e
  se `OPEN_BANKING_REDIRECT_URI`/`OPEN_BANKING_BASE_URL` non sono HTTPS.
- Dal 2026-11-07 il compose di sviluppo lega Postgres, Redis e API a `127.0.0.1` (solo il
  frontend resta sulla LAN); uvicorn parte con `--proxy-headers` fidandosi solo delle reti
  private; l'nginx del frontend risolve l'IP reale con `set_real_ip_from` (reti private:
  se il reverse proxy ha un IP pubblico va aggiunto in `frontend/nginx.conf`), non logga
  le query string e invia una CSP (la SPA non ha script inline: tema in `public/theme-init.js`;
  il Picker Google non e' stato provato con la CSP).
- Redis con password (opzionale, dal 2026-11-07): `REDIS_PASSWORD=<solo lettere/cifre>` e, con la STESSA
  password, `REDIS_URL=redis://:<password>@redis:6379/0` nel `.env`; poi `docker compose up -d`
  (ricrea redis, app e worker). Senza `REDIS_PASSWORD` il comportamento e' invariato.
- NON lanciare `docker compose config` senza filtrare: stampa il `.env` interpolato (SECRET_KEY compresa).
- Il log di errore di nginx puo' contenere la query di una richiesta fallita (upstream giu'):
  limite noto, riguarda anche `code`/`state` del callback bancario.

## Istanza locale dell'utente (SOLO SVILUPPO)
- Dal 2026-11-07 (detto dall'utente): lo stack locale e' di sola sviluppo, **i dati veri stanno nel
  container LXC di produzione** (a cui non si ha accesso). Prima la memoria lo dava per "dati reali".
- Container `lumio-app-1`, `lumio-worker-1`, `lumio-frontend-1` (:5173), `lumio-postgres-1`
  (:5432, DB `lumio`, dati di prova dell'utente), `lumio-redis-1`.
- Rebuild, restart e migration sono liberi (la migration si applica da sola all'avvio di `app`,
  dillo comunque). Non cancellare volumi/`down -v` senza chiedere; pytest sempre su DB effimeri
  (il TRUNCATE cancellerebbe i dati di prova); verifiche manuali con account `*-verify@example.com`.
- Per provare funzioni con configurazioni diverse senza toccare il `.env`: file compose di
  override con `environment:` (ha la precedenza su `env_file`), mai `docker compose config`.
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
- Dal 2026-10-31 (detto dall'utente): in produzione l'app gira in un **container LXC**
  Proxmox (non in una VM come raccomanda la guida). Non sono noti CTID, percorso, file
  compose in uso: chiederli prima di dare comandi di aggiornamento, non assumere `/opt/lumio`.

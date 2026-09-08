# Deploy self-hosted su Proxmox

Guida operativa per far girare Lumio su un'installazione Proxmox VE, con
Docker Compose. Copre due scenari:

- **Scenario A — tutto incluso**: Postgres e Redis girano come container
  insieme all'app (`docker-compose.yml`).
- **Scenario B — Postgres esterno già esistente**: si usa un'istanza
  Postgres che hai già in produzione altrove (`docker-compose.external-db.yml`).
  Vedi la sezione [Scenario B](#scenario-b--agganciarsi-a-un-postgres-già-esistente).

Il resto della guida (VM, Docker, HTTPS, backup, aggiornamenti) è comune ai
due scenari.

---

## 1. Scelta dell'ospite: VM o container LXC

**Raccomandazione: VM.**

Docker dentro un container LXC funziona (Debian + `nesting=1`, `keyctl=1`,
unprivileged), ma è una configurazione fragile: si rompe con gli aggiornamenti
del kernel Proxmox, con overlayfs su ZFS, e ai passaggi di versione di cgroup.
Per un'applicazione che custodisce dati finanziari personali, la VM è la
scelta noiosa e prevedibile — quella giusta.

Un LXC resta accettabile solo se hai già altri servizi Docker in LXC che
funzionano e sai gestire quella configurazione.

### Dimensionamento della VM

| Parametro | Valore consigliato | Note |
|---|---|---|
| OS | Debian 13 o Ubuntu 24.04 LTS (cloud image) | |
| vCPU | 2 | 4 se prevedi OCR o modelli AI locali |
| RAM | 4 GB | 2 GB bastano a regime, **ma non alla build** (vedi sotto) |
| Disco | 32 GB su SSD/NVMe | `discard=on`, controller VirtIO SCSI single |
| CPU type | `host` | |
| Rete | VirtIO, IP statico o DHCP reservation | serve fisso per il reverse proxy |
| QEMU Guest Agent | **abilitato** | necessario per backup/snapshot consistenti |

**Attenzione alla RAM in fase di build.** `npm run build` del frontend è la
parte più affamata del deploy: con 2 GB rischi un OOM kill durante
`docker compose build`. Se vuoi tenere la VM piccola, aggiungi swap (2 GB) o
builda le immagini su un'altra macchina e pubblicale su un registry privato.

---

## 2. Preparazione della VM

Sull'ospite appena creato, come root:

```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl git qemu-guest-agent
systemctl enable --now qemu-guest-agent
```

Docker Engine + plugin Compose (repo ufficiale, non quello di Debian):

```bash
curl -fsSL https://get.docker.com | sh
```

Verifica che il plugin compose ci sia (serve la v2, la guida usa la sintassi
`!reset` che richiede **Compose ≥ 2.24**):

```bash
docker compose version
```

Firewall minimo — solo SSH e la porta del reverse proxy:

```bash
apt install -y ufw
ufw allow OpenSSH
ufw allow from <IP-del-reverse-proxy> to any port 8080 proto tcp
ufw enable
```

Se il reverse proxy gira **sulla stessa VM** (opzione Caddy, sezione 6), non
serve aprire la 8080 verso l'esterno: apri 80 e 443.

---

## 3. Recupero del codice

```bash
mkdir -p /opt && cd /opt
git clone <url-del-tuo-remote> lumio
cd lumio
cp .env.example .env
```

Tieni `/opt/lumio` come unica copia: la procedura di aggiornamento (sezione 8)
è un `git pull` in questa directory.

---

## 4. Configurazione: `.env`

Apri `.env` e modifica **almeno** i valori seguenti. Nessuno di questi è
opzionale in produzione.

### 4.1 Ambiente

```ini
APP_ENV=production
```

> **Conseguenza da conoscere prima, non dopo:** con `APP_ENV=production` il
> cookie di refresh viene emesso con il flag `Secure`
> (`backend/app/api/v1/auth.py`). Su HTTP puro il browser lo scarta e **il
> login non funziona**. HTTPS non è un abbellimento: è un prerequisito.
> Vedi sezione 6.

### 4.2 Chiave di firma

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

```ini
SECRET_KEY=<il-valore-generato>
```

Cambiare `SECRET_KEY` in seguito invalida tutte le sessioni attive (effetto
collaterale utile: è la via per un logout forzato globale).

### 4.3 Password del database

**Scenario A** (Postgres nel compose):

```ini
POSTGRES_SUPERUSER=lumio_admin
POSTGRES_SUPERUSER_PASSWORD=<password-forte-1>
POSTGRES_DB=lumio
POSTGRES_APP_USER=lumio_app
POSTGRES_APP_PASSWORD=<password-forte-2>

DATABASE_URL=postgresql+asyncpg://lumio_app:<password-forte-2>@postgres:5432/lumio
```

`DATABASE_URL` deve usare il **ruolo applicativo**, mai il superuser: un
ruolo superuser o `BYPASSRLS` ignora sempre le policy di Row-Level Security,
rendendo l'isolamento multi-tenant puramente decorativo. Le due password
devono essere allineate: `POSTGRES_APP_PASSWORD` crea il ruolo,
`DATABASE_URL` ci si connette.

**Scenario B** (Postgres esterno): vedi sezione 7.

### 4.4 Branding

```ini
APP_NAME=Lumio
APP_TAGLINE=See your money clearly.
VITE_APP_NAME=Lumio
VITE_APP_TAGLINE=See your money clearly.
```

Le due varianti `VITE_*` sono duplicate per necessità: Vite espone al browser
solo le variabili con quel prefisso. Sono **build-time**: se le cambi devi
ricostruire l'immagine frontend (`--build`), non basta riavviare.

### 4.5 Porte

```ini
FRONTEND_PORT=8080
BACKEND_PORT=8000
```

`BACKEND_PORT` diventa irrilevante applicando l'override della sezione 5, che
smette di pubblicare il backend: il traffico API passa dall'nginx del
frontend, che proxa `/api/` verso il container `app` sulla rete interna
Docker. È così che il cookie di refresh resta same-site e non c'è CORS da
configurare.

### 4.6 Google Sheets (opzionale)

Se non usi l'integrazione, lascia `GOOGLE_ENABLED=false` e ignora il resto.
Se la usi:

```ini
GOOGLE_ENABLED=true
GOOGLE_CLIENT_ID=<...>
GOOGLE_CLIENT_SECRET=<...>
GOOGLE_REDIRECT_URI=https://lumio.tuodominio.tld/api/v1/integrations/google/callback
GOOGLE_PICKER_API_KEY=<...>
VITE_GOOGLE_PICKER_API_KEY=<lo-stesso-valore>
```

Il redirect URI deve puntare all'**origine pubblica HTTPS su cui navighi**
(quella del reverse proxy), non a quella del backend, e va registrato
identico nella console Google Cloud.

> Nota per lo Scenario B: `docker-compose.external-db.yml` non passa l'arg
> `VITE_GOOGLE_PICKER_API_KEY` alla build del frontend, a differenza del
> compose standard. Se usi Google Sheets con Postgres esterno, aggiungi quella
> riga sotto `frontend.build.args` (o mettila nell'override della sezione 5).

---

## 5. Avvio in produzione

I file compose principali sono tarati sullo sviluppo locale: pubblicano i
datastore sull'host (comodo per `pytest`, `psql`, una GUI) e non prevedono un
reverse proxy davanti. Gli override di produzione sono **già nel
repository**, così i file base restano aggiornabili con `git pull`:

| File | Contenuto |
|---|---|
| `docker-compose.prod.yml` | hardening comune: nessuna porta pubblicata tranne il frontend su `127.0.0.1`, log rotation su tutti i servizi |
| `docker-compose.prod.local-db.yml` | solo Scenario A: chiude anche la porta del Postgres containerizzato |

Richiedono **Docker Compose ≥ 2.24** (tag `!reset` / `!override`).

### 5.1 Cosa fanno, e perché

`docker-compose.yml` pubblica 5432 (Postgres) e 6379 (Redis) sull'host:
sbagliato su una VM raggiungibile dalla LAN. **Redis in questo setup non ha
autenticazione**, quindi chiunque sulla rete potrebbe leggere e manipolare la
coda dei job. Anche il backend viene tolto dalle porte pubblicate: il traffico
API passa dall'nginx del frontend, che proxa `/api/` sulla rete interna
Docker — è così che il cookie di refresh resta same-site e non c'è CORS da
configurare.

Gli override aggiungono anche **log rotation** (`max-size: 10m`,
`max-file: 5`). Senza limiti il log di un container cresce fino a riempire il
disco: su un self-hosted senza log rotation esterna è il modo più comune di
far cadere il servizio dopo mesi di uptime.

Il frontend viene legato a `127.0.0.1`, presupponendo un reverse proxy sulla
**stessa** macchina. Se il proxy gira altrove, togli il prefisso in
`docker-compose.prod.yml` (`"${FRONTEND_PORT:-8080}:80"`) e proteggi la porta
con `ufw` come nella sezione 2.

### 5.2 Comando di avvio

**Scenario A** — servono entrambi gli override:

```bash
cd /opt/lumio
docker compose -f docker-compose.yml \
               -f docker-compose.prod.yml \
               -f docker-compose.prod.local-db.yml up -d --build
```

**Scenario B** — nessun Postgres containerizzato da chiudere:

```bash
cd /opt/lumio
docker compose -f docker-compose.external-db.yml \
               -f docker-compose.prod.yml up -d --build
```

Non usare `docker-compose.prod.local-db.yml` nello Scenario B: definirebbe un
servizio `postgres` senza immagine né build context, facendo fallire il
comando.

Per non ripetere i `-f` ogni volta:

```bash
echo 'export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml:docker-compose.prod.local-db.yml' >> ~/.bashrc
```

### 5.3 Verifica che l'override abbia fatto effetto

Non darlo per scontato: Compose **concatena** le liste `ports` dei file
sovrapposti invece di sostituirle, quindi un override scritto senza i tag
`!reset`/`!override` lascia attivo il binding del file base *accanto* al
nuovo, e la porta resta aperta sulla LAN. Controlla il risultato del merge:

```bash
docker compose config --format json \
  | python3 -c 'import json,sys; [print(n, [f"{p.get(\"host_ip\",\"\")}:{p[\"published\"]}" for p in s.get("ports",[])]) for n,s in json.load(sys.stdin)["services"].items()]'
```

Ti aspetti una sola riga con una porta, quella del `frontend`, su
`127.0.0.1`. Tutto il resto deve avere la lista vuota.

Le migration Alembic vengono applicate automaticamente all'avvio del **solo**
servizio `app` (`alembic upgrade head` nel `CMD` del Dockerfile); il `worker`
sovrascrive il comando e non le esegue, per evitare migration concorrenti.
Quindi non lanciare mai due repliche di `app` in parallelo.

### 5.4 Verifica dello stato

```bash
docker compose ps
docker compose logs -f app
```

Gli endpoint di salute sono sulla **radice** del backend, non sotto
`/api/v1/`, quindi non passano dall'nginx del frontend. Interrogali da dentro
la rete Docker:

```bash
docker compose exec app python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/ready').read())"
```

`/health` è liveness (il processo risponde), `/ready` verifica che Postgres e
Redis siano raggiungibili.

---

## 6. HTTPS e reverse proxy

Obbligatorio, per il flag `Secure` sul cookie di refresh (sezione 4.1).

### Requisiti del proxy, qualunque scelga

- `client_max_body_size` (o equivalente) ≥ 20 MB. L'nginx interno del
  frontend è già configurato così; il proxy davanti **non** lo eredita, e un
  suo limite più basso produce lo stesso `413` sugli import di estratti conto
  un po' grossi
- **buffering delle risposte disattivato** sul path `/api/`: l'app usa SSE per
  il progresso dei job di import, e un proxy che bufferizza congela la barra
  di avanzamento fino alla fine del job
- inoltro di `X-Forwarded-Proto: https`
- timeout di lettura generoso (≥ 300s, in linea con
  `IMPORT_JOB_TIMEOUT_SECONDS`)

### Opzione 1 — proxy esterno già esistente

Se hai già Nginx Proxy Manager, Traefik o simili in un LXC dedicato, aggiungi
un host che punta a `http://<ip-vm-lumio>:8080`. Su NPM: scheda *Advanced*,

```nginx
client_max_body_size 20m;
proxy_buffering off;
proxy_read_timeout 300s;
```

### Opzione 2 — Caddy sulla stessa VM

Il percorso più corto se non hai già un proxy. Crea un **terzo** file di
override, `/opt/lumio/docker-compose.caddy.yml` (tenerlo separato lascia
`docker-compose.prod.yml` aggiornabile con `git pull`):

```yaml
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - frontend
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:
```

`/opt/lumio/Caddyfile`:

```
lumio.tuodominio.tld {
    reverse_proxy frontend:80 {
        flush_interval -1
    }
    request_body {
        max_size 20MB
    }
}
```

`flush_interval -1` disabilita il buffering: è la riga che tiene vive le SSE.
Con questa opzione il mapping del frontend può restare su `127.0.0.1`, perché
Caddy lo raggiunge dalla rete Docker interna.

Aggiungi il file alla catena degli override, per ultimo:

```bash
docker compose -f docker-compose.yml \
               -f docker-compose.prod.yml \
               -f docker-compose.prod.local-db.yml \
               -f docker-compose.caddy.yml up -d --build
```

### Certificati

- **Dominio pubblico**: Let's Encrypt HTTP-01 automatico (Caddy non richiede
  configurazione).
- **Dominio interno non raggiungibile da Internet**: usa DNS-01 con il tuo
  provider DNS. È la via più semplice per un certificato valido senza esporre
  la porta 80.
- Un certificato self-signed funziona (il flag `Secure` guarda lo schema
  `https`, non la validità), ma vale solo se accetti di istruire ogni browser
  a fidarsi.

---

## 7. Scenario B — agganciarsi a un Postgres già esistente

Questo è il caso in cui hai già un'istanza Postgres in produzione (altra VM,
altro LXC, o un server dedicato) e vuoi che Lumio ci scriva dentro, senza un
secondo Postgres nel compose.

Il file da usare è `docker-compose.external-db.yml`: identico allo standard,
senza il servizio `postgres`. Redis resta containerizzato (serve solo come
coda dei job, non contiene dati da preservare a lungo).

### 7.1 Verifica di compatibilità dell'istanza

| Requisito | Perché |
|---|---|
| **Postgres ≥ 13** | le migration usano `gen_random_uuid()`, built-in da 13 (prima serviva `pgcrypto`). Testato su 16. |
| Possibilità di **creare ruoli** (accesso amministrativo, una volta sola) | i due ruoli non sono creati dalle migration |
| Possibilità di creare un **database dedicato** | Lumio non deve condividere un DB con altre applicazioni: le policy RLS e le funzioni `SECURITY DEFINER` vivono nello schema `public` |
| Connessioni in ingresso dalla VM | `listen_addresses` + `pg_hba.conf`, sezione 7.4 |

Nessuna extension da installare.

### 7.2 Creare i ruoli — il passo che non puoi saltare

Lo script `db/postgres-init/01-create-app-role.sh` gira **solo** alla prima
inizializzazione del container Postgres dello Scenario A. Con un Postgres
esterno quei ruoli vanno creati a mano, una volta, come utente amministrativo.
Le migration danno per scontato che esistano già e falliscono altrimenti.

Servono **due** ruoli, non uno:

- `lumio_app` — il ruolo di runtime: `LOGIN`, **`NOSUPERUSER NOBYPASSRLS`**.
  È quello di `DATABASE_URL`. Se fosse superuser o `BYPASSRLS`, tutta la RLS
  dell'app sarebbe inerte.
- `lumio_rls_helper` — `NOLOGIN` ma **`BYPASSRLS`**. Non serve a connettersi:
  è il proprietario delle funzioni `SECURITY DEFINER` usate *dentro* le policy
  (`is_workspace_member`, `is_workspace_owner`, i trigger di coerenza
  workspace). Senza `BYPASSRLS` vero, una policy su `workspace_members`
  dovrebbe valutare la RLS della stessa tabella per decidere se applicare la
  RLS della stessa tabella: ricorsione. Un proprietario "normale" non basta,
  perché `FORCE ROW LEVEL SECURITY` toglie l'esenzione anche al proprietario.

Come amministratore sull'istanza esistente:

```sql
CREATE ROLE lumio_app WITH LOGIN PASSWORD '<password-forte>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

CREATE ROLE lumio_rls_helper
    WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;

GRANT lumio_rls_helper TO lumio_app;

CREATE DATABASE lumio OWNER lumio_app;
```

Poi, **connesso al database `lumio`**:

```sql
\c lumio
GRANT CREATE ON SCHEMA public TO lumio_rls_helper;
```

Tre note sul perché di ogni pezzo:

- `GRANT lumio_rls_helper TO lumio_app` è necessario perché le migration
  eseguono `ALTER FUNCTION ... OWNER TO lumio_rls_helper`, e Postgres consente
  di cedere la proprietà solo a un ruolo di cui chi esegue l'`ALTER` è membro.
- `GRANT CREATE ON SCHEMA public TO lumio_rls_helper` serve perché lo stesso
  `ALTER ... OWNER` richiede che il **nuovo** proprietario abbia `CREATE`
  sullo schema, non solo chi esegue il comando.
- `OWNER lumio_app` sul database: da Postgres 15 lo schema `public` è di
  `pg_database_owner`, di cui il proprietario del DB è membro implicito.
  Quindi `lumio_app` può creare tabelle senza grant aggiuntivi.

Se invece **devi riusare un database esistente** che non è di proprietà di
`lumio_app` (sconsigliato, ma capita), aggiungi:

```sql
\c <nome-db-esistente>
GRANT ALL ON SCHEMA public TO lumio_app;
GRANT CREATE ON SCHEMA public TO lumio_rls_helper;
```

e verifica che non ci siano già tabelle con i nomi usati da Lumio
(`users`, `workspaces`, `transactions`, `accounts`, ...).

### 7.3 `DATABASE_URL`

```ini
DATABASE_URL=postgresql+asyncpg://lumio_app:<password-forte>@<host>:5432/lumio
```

Il driver è **`asyncpg`**, non `psycopg2`: lo schema dell'URL fa parte della
configurazione, non è cosmetico.

Il valore di `<host>` dipende da dove sta Postgres **rispetto al container**,
non rispetto alla VM:

| Postgres gira... | `<host>` da usare |
|---|---|
| in un altro LXC / altra VM / altro server | l'IP o l'hostname di rete (es. `192.168.1.20`) |
| sulla **stessa VM**, come servizio di sistema (non in Docker) | `172.17.0.1` (gateway del bridge Docker), oppure `host.docker.internal` aggiungendo `extra_hosts: ["host.docker.internal:host-gateway"]` ai servizi `app` e `worker` |
| in un container Docker sulla stessa VM, altro compose | collega i due stack a una rete Docker esterna comune e usa il nome del servizio |

Un hostname è preferibile a un IP: se un domani sposti il database, cambi il
DNS e non il `.env`.

Se il traffico verso Postgres attraversa una rete non fidata, aggiungi
`?ssl=require` alla query string dell'URL (`asyncpg` la interpreta) e abilita
`ssl = on` lato server.

### 7.4 Consentire la connessione lato Postgres

Sull'host Postgres, in `postgresql.conf`:

```ini
listen_addresses = '*'          # oppure l'IP specifico dell'interfaccia
```

In `pg_hba.conf`, una riga il più stretta possibile — l'IP della VM Lumio,
solo il database `lumio`, solo il ruolo `lumio_app`, con `scram-sha-256`:

```
# TYPE  DATABASE  USER        ADDRESS            METHOD
host    lumio     lumio_app   192.168.1.50/32    scram-sha-256
```

Non usare `0.0.0.0/0`, e non usare `trust` "solo per provare": è la
configurazione che poi resta.

Ricarica: `systemctl reload postgresql` (o `SELECT pg_reload_conf();`).

Verifica dalla VM Lumio, **prima** di avviare il compose:

```bash
docker run --rm postgres:16-alpine psql "postgresql://lumio_app:<password>@<host>:5432/lumio" -c "select current_user, version();"
```

Se questo comando non funziona, l'app non partirà: risolvi qui, dove il
messaggio d'errore è leggibile, invece che nei log del container.

### 7.5 Avvio

```bash
cd /opt/lumio
export COMPOSE_FILE=docker-compose.external-db.yml:docker-compose.prod.yml
docker compose up -d --build
docker compose logs -f app
```

Al primo avvio `app` esegue `alembic upgrade head` sull'istanza esterna: nei
log devi vedere la sequenza delle migration da `0001` in avanti. Un errore su
`lumio_rls_helper` a questo punto significa che il passo 7.2 non è stato
completato.

### 7.6 Verifica che la RLS sia davvero attiva

Questo controllo vale la pena farlo una volta, perché un `DATABASE_URL`
puntato per sbaglio a un ruolo privilegiato non dà **nessun** errore visibile —
semplicemente l'isolamento tra workspace non c'è più:

```sql
SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'lumio_app';
```

Devono essere entrambi `false`. Se non lo sono, correggi il ruolo
(`ALTER ROLE lumio_app NOSUPERUSER NOBYPASSRLS;`) o `DATABASE_URL`.

---

## 8. Backup

Le due strategie servono a scenari diversi e non si sostituiscono a vicenda.

### 8.1 Backup della VM (Proxmox)

Configura un job in *Datacenter → Backup* verso un datastore **separato dal
disco della VM** (Proxmox Backup Server o storage NFS/CIFS), modalità
*snapshot*, con Guest Agent attivo — è il fs-freeze del guest agent a rendere
lo snapshot consistente.

Da solo però non basta: uno snapshot a caldo di Postgres è un backup
*crash-consistent*. Si recupera quasi sempre, ma "quasi" non è la parola che
vuoi sentire sui tuoi dati patrimoniali.

### 8.2 Dump logico del database

È quello che ti salva da una migration andata male, dove lo snapshot della VM
ti riporterebbe indietro anche tutti i dati inseriti dopo.

**Scenario A** (Postgres nel compose) — `/usr/local/bin/lumio-backup.sh`:

```bash
#!/bin/bash
set -euo pipefail
cd /opt/lumio
DEST=/var/backups/lumio
mkdir -p "$DEST"
STAMP=$(date +%F-%H%M)

export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml:docker-compose.prod.local-db.yml

docker compose exec -T postgres pg_dump -U lumio_admin -d lumio -Fc \
  > "$DEST/db-$STAMP.dump"

docker run --rm -v lumio_storage:/data:ro -v "$DEST":/backup alpine \
  tar czf "/backup/storage-$STAMP.tar.gz" -C /data .

cp .env "$DEST/env-$STAMP.bak"
find "$DEST" -type f -mtime +30 -delete
```

**Scenario B** (Postgres esterno): salta il primo comando e includi il
database di Lumio nel backup che già fai sull'istanza esterna — verificando
che quel backup lo copra davvero, un DB nuovo non entra automaticamente in
tutti gli script. Il `pg_dump` puoi anche lanciarlo dalla VM Lumio:

```bash
docker run --rm postgres:16-alpine pg_dump \
  "postgresql://lumio_app:<password>@<host>:5432/lumio" -Fc \
  > /var/backups/lumio/db-$(date +%F).dump
```

**Il volume `storage` va salvato in entrambi gli scenari**: contiene i file
importati (PDF degli estratti conto). Non è nel database, e non è
ricostruibile.

Cron giornaliero:

```bash
chmod +x /usr/local/bin/lumio-backup.sh
echo '15 3 * * * root /usr/local/bin/lumio-backup.sh' > /etc/cron.d/lumio-backup
```

Il file `.env` va nel backup perché contiene `SECRET_KEY` e le credenziali:
senza di lui un ripristino del database non ti ridà un'app funzionante.
Trattalo come materiale sensibile (permessi `600`, destinazione cifrata).

### 8.3 Restore

```bash
docker compose exec -T postgres \
  pg_restore -U lumio_admin -d lumio --clean --if-exists < db-2026-09-08-0315.dump
```

(con `COMPOSE_FILE` esportato come nella sezione 5.2; nello Scenario B il
`pg_restore` va lanciato contro l'istanza esterna, non via `compose exec`)

Provalo una volta su una VM di test **adesso**, non il giorno in cui ti
serve. Un backup non verificato è un'ipotesi.

---

## 9. Aggiornamenti

```bash
cd /opt/lumio
/usr/local/bin/lumio-backup.sh          # sempre, prima
git pull
docker compose up -d --build            # con COMPOSE_FILE esportato (§5.2)
docker compose logs -f app              # controlla le migration
```

Il backup prima dell'aggiornamento non è prudenza teorica: le migration
Alembic hanno un `downgrade`, ma nella pratica un rollback di schema su dati
reali è un'operazione da evitare — il dump è la via d'uscita affidabile.

Se hai modificato `VITE_APP_NAME` o le altre variabili build-time, `--build`
è obbligatorio: sono compilate nel bundle, non lette a runtime.

Pulizia periodica delle immagini vecchie:

```bash
docker image prune -f
```

---

## 10. Checklist finale

Prima di considerare il deploy concluso:

- [ ] `APP_ENV=production` **e** HTTPS funzionante (login riuscito da browser)
- [ ] `SECRET_KEY` rigenerata, non quella dell'esempio
- [ ] `docker compose config` mostra una sola porta pubblicata, il frontend su `127.0.0.1` (§5.3)
- [ ] Porte 5432 e 6379 **non** raggiungibili dalla LAN (`nmap` dalla tua macchina)
- [ ] `DATABASE_URL` usa `lumio_app`, e `rolsuper`/`rolbypassrls` sono `false` (§7.6)
- [ ] `client_max_body_size` ≥ 20 MB anche sul reverse proxy (sull'nginx interno è già impostato)
- [ ] Import di un PDF > 1 MB riuscito, con barra di progresso che avanza in tempo reale (verifica SSE + limite upload in un colpo)
- [ ] `/ready` risponde `ok` per database e redis
- [ ] Backup notturno schedulato e **restore provato almeno una volta**
- [ ] `.env` con permessi `600` e incluso nel backup
- [ ] QEMU Guest Agent attivo (Proxmox mostra l'IP della VM nel riepilogo)

---

## Riferimenti nel repository

- `docker-compose.yml` — Scenario A (Postgres e Redis inclusi)
- `docker-compose.external-db.yml` — Scenario B (Postgres esterno)
- `docker-compose.prod.yml` — override di produzione, comune ai due scenari
- `docker-compose.prod.local-db.yml` — override aggiuntivo, solo Scenario A
- `db/postgres-init/01-create-app-role.sh` — i ruoli da replicare a mano nello Scenario B
- `.env.example` — elenco commentato di tutte le variabili
- `frontend/nginx.conf` — proxy interno verso il backend, limite di upload
- `backend/Dockerfile` — dove gira `alembic upgrade head`

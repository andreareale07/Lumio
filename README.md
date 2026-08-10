# Lumio

**See your money clearly.**

Personal finance & wealth management, self-hosted e privacy-first.

> Questo README è minimale (milestone 01 — Foundation). La documentazione completa
> (`ARCHITECTURE.md`, `DEPLOYMENT.md`, `DATABASE.md`, `SECURITY.md`, `API.md`, ecc.)
> arriva con la milestone 12 — vedi [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Avvio rapido (modalità standard)

Requisiti: Docker e Docker Compose.

```bash
cp .env.example .env
docker compose up -d
```

Servizi avviati: `app` (backend FastAPI), `worker`, `postgres`, `redis`, `frontend`.

Verifica che il backend sia attivo:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Modalità power user (PostgreSQL esterno)

```bash
cp .env.example .env
# modifica DATABASE_URL in .env per puntare al tuo Postgres esterno
docker compose -f docker-compose.external-db.yml up -d
```

## Sviluppo locale (senza Docker)

Vedi [`backend/`](backend/) e [`frontend/`](frontend/) per i rispettivi setup.

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -r requirements-dev.txt   # o .venv/bin/pip su macOS/Linux
ruff check .
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run lint
npm run test        # vitest
npm run test:e2e    # playwright (richiede `npx playwright install` la prima volta)
```

## Documentazione di progetto

- Specifica completa: [`docs/SPEC.md`](docs/SPEC.md)
- Roadmap e milestone: [`docs/ROADMAP.md`](docs/ROADMAP.md)

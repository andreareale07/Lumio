# Lumio

Personal finance & wealth management app — self-hosted, privacy-first, multi-tenant.
Payoff: "See your money clearly." Nome prodotto sempre via config (`APP_NAME`), mai hardcoded.

## Stack

- Backend: Python 3.x, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic, PostgreSQL, Redis, worker async
- Frontend: React, TypeScript, Vite, mobile-first, PWA-ready
- Deploy: Docker Compose (profilo standard + profilo external-db)
- API: REST/HTTP versionato (`/api/v1/...`) + SSE/WebSocket per job/progress

## Architettura

Modular monolith. Niente microservizi in questa fase. Interfacce astratte per tutto ciò
che in futuro potrebbe diventare un servizio separato: `BankParser`, `AIProvider`,
`MarketDataProvider`, `StorageProvider`, `ExportProvider`.

## Regole non negoziabili

- Isolamento multi-tenant SEMPRE a doppio livello: check applicativo (ownership) + PostgreSQL Row-Level Security. Non fidarsi solo di `if x.user_id == current_user.id`.
- Mai `Base.metadata.create_all()` in produzione — solo Alembic, migration versionate.
- Mai SQLite in produzione — solo PostgreSQL.
- AI sempre opzionale — l'app deve funzionare al 100% con `AI_PROVIDER=none`.
- API key/secret cifrati a riposo, mai in log, mai restituiti dalle API, mascherati in UI.
- Operazioni lunghe (parsing PDF, OCR, classificazione AI, export, import grandi) → sempre job async via Redis/worker + eventi SSE/WebSocket. Mai bloccare la request HTTP.
- Conservare sempre il dato raw insieme al normalizzato (`description_raw` non si tocca mai).
- Un trasferimento interno tra conti dello stesso workspace non è mai spesa né entrata.
- Le correzioni manuali dell'utente hanno sempre priorità sull'AI.

## Workflow di sviluppo

Si procede per milestone verificabili (vedi `docs/ROADMAP.md`), non per feature sparse.
Ogni milestone si considera chiusa solo secondo la Definition of Done in `docs/ROADMAP.md`.

Prima di ogni feature importante:
1. analizza cosa esiste già, non duplicare
2. valuta impatto su modello dati, sicurezza, UX
3. se un requisito importante non è definito → non inventare, segnala `DECISION REQUIRED`
   con 2-3 alternative (pro/contro/impatto); per dettagli minori scegli e documenta

## Riferimenti

- Spec completa (fonte di verità, non modificare): `docs/SPEC.md`
- Milestone e Definition of Done: `docs/ROADMAP.md`

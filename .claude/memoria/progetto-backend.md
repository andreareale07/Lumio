# Progetto: backend (FastAPI + worker arq)

Percorso: `backend/`. Python 3.12. Un solo pacchetto `app/` usato sia dal servizio `app`
(uvicorn) sia dal `worker` (arq, `app.worker.main.WorkerSettings`): stessa immagine Docker.

## Struttura (solo cio' che non si capisce dai nomi)
- `app/api/v1/` endpoint REST; `router.py` monta i router. Il router Google e' montato
  **una sola volta all'import** di `app.main` (`if get_settings().google_enabled`): cambiare
  l'env a runtime non basta, serve riavviare (e nei test va settato prima dell'import).
- `app/services/` logica di dominio. Convenzione: `*_calc.py` = funzioni **pure** senza DB
  (testabili senza Postgres: `tax_lot_calc`, `position_calc`, `recurrence_calc`,
  `anomaly_calc`, `analytics_calc`, `corporate_action_calc`); `*_service.py` = DB-aware.
- `app/worker/queue.py` accoda i job, `app/worker/jobs/` li esegue -> vedi
  `guida-job-asincroni.md`.
- `app/db/rls.py`: `set_rls_current_user` / `rls_session` (identita' RLS) -> vedi
  `progetto-database-rls.md`.
- Interfacce astratte (regola CLAUDE.md): `BankParser` (`app/parsers/base.py`),
  `AIProvider` (`app/ai/`), `MarketDataProvider` (`app/marketdata/`), `StorageProvider`
  (`app/storage/`), `TaxJurisdiction` (`app/tax/base.py`).
- `app/core/config.py`: `get_settings()` e' `lru_cache`d -> qualunque override d'ambiente
  nei test deve avvenire prima del primo import di `app.main` (per questo esiste
  `backend/conftest.py` alla radice, non in `tests/`).
- `backend/scripts/`: script una tantum (`recompute_positions.py`, `gen_taxonomy.py`,
  `fix_asset_price_currency.py`).

## Convenzioni
- Commenti e docstring in italiano, con apostrofo al posto delle accentate (`e'`, `piu'`).
- Modelli con `server_default`/`onupdate`: `__mapper_args__ = {"eager_defaults": True}`,
  cosi' `id`/`created_at`/`updated_at` tornano via `RETURNING` senza `refresh()` dopo il commit.
- Configurazioni "da provare/confrontare" (provider AI, market data, mapping import) =
  **lista di profili nominati con attivazione esplicita**, mai un record unico
  sovrascritto (precedenti: `ImportMapping`, `AIProfile`, `MarketDataProfile`).
  Eccezione deliberata: `google_integrations` (un solo account per workspace).
- Nessun SDK esterno per Google/market data: REST diretto via `httpx`.
- Validazioni duplicate frontend (zod) + backend (pydantic): il backend deve sempre
  validare da se' (es. IBAN).

## Punti pericolosi
- **Mai una query su tabelle RLS dopo `await db.commit()` nella stessa sessione** (errore
  ricorrente n.1 del progetto) -> `progetto-database-rls.md`.
- Errori `TaxRulesetNotFound` mappati a 400 da un handler globale in `main.py`.
- Testo generato dal backend (nomi job in `job_registry.py`, categorie di sistema in
  `app/classification/catalog.py`) e' in **italiano hardcoded**: limite accettato e
  documentato (opzione "c" di una DECISION REQUIRED del 2026-08-21), non tradurlo senza
  una decisione esplicita.

## Comandi (da `backend/`, venv in `backend/.venv`)
- Lint: `./.venv/Scripts/python.exe -m ruff check .`
- Test: vedi `guida-metodo-sviluppo-e-test.md` (mai sul DB `lumio`).
- Migration: `alembic revision -m "..."`, `alembic upgrade head`; il container `app` fa
  `alembic upgrade head` all'avvio (Dockerfile `CMD`).

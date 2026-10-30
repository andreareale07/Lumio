# Lumio

Personal finance & wealth management, self-hosted, privacy-first, multi-tenant ("See your money clearly").
Repo unico (`github.com/andreareale07/Lumio`): `backend/` FastAPI + Pydantic + SQLAlchemy 2 + Alembic + worker arq,
`frontend/` React + TS + Vite (PWA, mobile-first, it/en), PostgreSQL 16 + Redis 7, Docker Compose. Modular monolith.
Lingua di lavoro: italiano (conversazione, commenti, commit, docs); identificatori del codice in inglese.
Fonti di verita': `docs/SPEC.md` (non modificare), `docs/ROADMAP.md` (milestone e Definition of Done).

## Memoria del progetto
Prima di iniziare un'attivita' leggi, senza che l'utente lo chieda, i file indicati dalla tabella (e solo quelli).
Tienile aggiornate: se scopri un fatto nuovo non ovvio dal codice, o uno scritto li' e' sbagliato, correggi la scheda a fine attivita'.

| Se l'attivita' riguarda... | Leggi (in `.claude/memoria/`) |
|---|---|
| Qualsiasi modifica backend | `progetto-backend.md`, `progetto-database-rls.md` |
| Migration, nuove tabelle, query, RLS | `progetto-database-rls.md` |
| Qualsiasi modifica frontend | `progetto-frontend.md`, `guida-ux-e-design.md` |
| Nuova pagina, lista, configurazione | `guida-ux-e-design.md` |
| Test, verifica, preparare un commit | `guida-metodo-sviluppo-e-test.md`, `procedura-gestione-branch.md` |
| Job lunghi, worker, SSE, interruzioni | `guida-job-asincroni.md` |
| Import, parser, dedup, trasferimenti, tipi transazione | `guida-import-e-movimenti.md` |
| Portfolio, prezzi, rendimenti, fiscalita' | `guida-investimenti-e-fiscalita.md` |
| AI, Google Sheets | `guida-ai-e-integrazioni.md` |
| Docker, deploy, `.env`, istanza locale | `guida-deploy.md` |

Manutenzione della memoria:
- A fine attivita', se hai scoperto qualcosa di non ovvio, aggiorna la scheda giusta (o creane una e aggiungi la riga in tabella). Dimmi cosa hai aggiornato.
- "Aggiungi in memoria quanto imparato" = linee guida per TIPO di attivita', generaliste; i casi specifici vanno in una scheda `task-*`.
- Un fatto in una sola scheda, le altre rimandano. Correggi subito cio' che e' sbagliato/obsoleto; date sempre assolute.
- Mai salvare segreti, password, connection string, token. Tieni questo file corto: il dettaglio va nelle schede.
- Le preferenze di lavoro generali dell'utente vanno anche nell'auto-memory personale (`feedback-*.md`).

## Mappa in breve
```
 browser ──> frontend (nginx :5173, SPA) ──/api/──> app (FastAPI :8000, /api/v1, SSE)
                                                      │  enqueue (arq)      │ SQL come lumio_app
                                                      ▼                     ▼
                       Redis (code, job_events, cache quote, cancel) <── worker (arq)
                                                      │                     │
                                                      └──> PostgreSQL (RLS FORCE su ogni tabella di workspace)
 worker/app ──> provider esterni opzionali: AI (Anthropic/OpenAI/Ollama), market data (Yahoo/Stooq), Google API
 import: upload ─> resolve-account ─> confirm ─> import_job (parser ─> dedup ─> transfer ─> classify ─> persist)
 investment_transactions ─> positions (derivate) ─> snapshot patrimonio / lotti fiscali ─> zainetto (derivato)
```

## Regole valide sempre
1. Isolamento multi-tenant a doppio livello: check di ownership + RLS PostgreSQL. Mai fidarsi del solo `if x.user_id == ...`.
2. Mai query su tabelle RLS dopo `await db.commit()` nella stessa sessione (`SET LOCAL` scade): l'errore piu' ricorrente.
3. Solo migration Alembic versionate (mai `create_all()`), solo PostgreSQL (mai SQLite fuori dai test); tabella nuova = ENABLE+FORCE RLS + 4 policy + test.
4. AI sempre opzionale (`AI_PROVIDER=none` = app al 100%); le correzioni manuali vincono sempre su AI e regole.
5. Operazioni lunghe sempre in job async (worker + SSE), mai nella request; mai `_job_id` fisso per job rilanciabili.
6. `description_raw` e dati grezzi non si toccano mai; un trasferimento interno non e' mai spesa ne' entrata.
7. Segreti cifrati a riposo, mai in log/API, mascherati in UI. Non leggere ne' stampare `.env`. Nei test solo dati sintetici.
8. Nome prodotto solo via config (`APP_NAME`/`VITE_APP_NAME`), mai hardcoded. Interfacce astratte per parser/AI/market data/storage/export/fiscalita'.
9. Requisito importante non definito -> `DECISION REQUIRED` con 2-3 alternative (pro/contro/impatto); dettagli minori: scegli e documenta.
10. Ogni milestone user-facing include il frontend; `SPEC.md` vince su `SPEC_FE.md`. Prima di progettare cerca cio' che esiste gia'.
11. Git: si lavora su `master`; commit SOLO su richiesta esplicita, push mai senza richiesta; commit in italiano `tipo(scope): ...`, MAI `Co-Authored-By`.
12. Encoding: file UTF-8 senza BOM; in commit e commenti apostrofo al posto delle accentate (`attivita'`), UI/locales/docs con accenti.
13. Test: completare la fetta, poi verificare una volta; pytest SOLO su Postgres/Redis effimeri, MAI sul DB `lumio` (TRUNCATE).
14. Stack Docker locale = dati reali dell'utente: rebuild/restart liberi, mai cancellare dati/volumi; nessun accesso a produzione.

## Stato noto (verificare, puo' essere cambiato)
- Al 2026-10-30: `master` a `7f61e30`, pulito. Milestone 01-11 fatte, 12 (packaging + documentazione) aperta.
- Al 2026-10-30: `TradeRepublicParser.extract_account_info` e' ancora uno stub (formato IBAN titolare mai verificato su PDF reale).
- Al 2026-10-30: E2E Playwright non risultano rieseguiti dopo il dedup engine (2 golden-path rotti al 2026-08-21); test dedicati del motore a lotti da verificare (esiste `test_tax_calc.py`).
- Al 2026-10-30: da pulire con ok dell'utente: 5 worktree `agent-*` orfani su `2280394`, cartelle `db/postgres-init;C/` e `backend/features/settings/` (artefatti di path), `Lumio.tar.gz`.
- Richiesto dall'utente dopo M12, non pianificato: ruolo admin di istanza con "Impostazioni istanza" (config fuori da `.env`, audit log) e restyle menu Impostazioni.

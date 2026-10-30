# Guida: classificazione AI e integrazione Google Sheets

## Classificazione
- Pipeline: correzione manuale > regole (`rules_engine.py`, per priorita') > catalogo
  deterministico + merchant extraction > AI opzionale. Le correzioni manuali vincono
  **sempre**. Il suggerimento "crea regola" scatta dopo correzioni **ripetute** (soglia 2,
  SPEC §29), non dopo una sola.
- `AI_PROVIDER=none` deve lasciare l'app funzionante al 100%.
- I provider AI sono profili nominati (`AIProfile`), con uno solo attivo alla volta.
- Lingua di classificazione impostabile per conto.
- Errori e mancate esecuzioni dell'AI vanno nel registro `ai_run_events` (Impostazioni >
  Motore AI), non solo nel log del worker, che l'utente non vede.
- Interruzione cooperativa -> `guida-job-asincroni.md`.

## Google Sheets (M10)
- **OAuth per istanza**: ogni installazione self-hosted crea un proprio progetto Google
  Cloud, perche' il `redirect_uri` deve combaciare esattamente. Guida passo per passo
  nell'app (`IntegrationsSettingsPage.tsx`, `SetupGuide`). Vanno abilitate **3 API**:
  Sheets, Drive e Picker (Picker a parte, altrimenti non compare tra le restrizioni della
  chiave).
- `GOOGLE_ENABLED=false` di default: nessuna voce di menu, endpoint 404.
- `GET /connect` restituisce un JSON `{authorize_url}`, non un redirect: serve il bearer per
  firmare lo `state` (JWT, 10 minuti). `/callback` invece e' un redirect non autenticato.
- Scope minimi `drive.file openid email`. Credenziali cifrate in un unico blob JSON.
  `picker-token` restituisce solo l'access token (unica eccezione voluta alla regola "mai
  token dall'API").
- Unica eccezione alla regola "nessun retry": un solo retry su 429/503
  (`integrations/google/http.py`). Gli errori riportano il **corpo** della risposta
  (`raise_for_status_with_body`).
- `addChart` non e' idempotente: a ogni export si cancellano e si ricreano i grafici,
  ripristinando la posizione scelta dall'utente tramite abbinamento per **titolo**.
- `MeResponse.google_enabled` si costruisce in 3 punti di `auth.py`: se se ne dimentica uno,
  ~150 test falliscono con errori pydantic.
- Negli E2E, un redirect simulato cross-origin richiede un URL **assoluto**.

## Debito noto
L'export e' solo on demand e crea il foglio (non si puo' scegliere un foglio esistente).
Il client OAuth sta in `.env`: e' prevista una futura sezione "Impostazioni istanza" per
admin (vedi Stato noto in CLAUDE.md).

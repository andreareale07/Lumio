# Task: app mobile (PWA + guscio Capacitor Android)

Decisione 2026-11-07 (utente su Android, iOS dopo): stesso frontend React in un guscio Capacitor con schermata
"Server" (URL self-hosted); la PWA resta come fallback. Guida utente e build: `docs/mobile-app.md`.

## Fatto (2026-11-07, non committato, mai provato su un telefono)
- **PWA**: `vite-plugin-pwa` (registerType "prompt", API MAI in cache), manifest col nome da `VITE_APP_NAME`,
  icone PNG in `frontend/public/` (System.Drawing, NON npx remoto: bloccato), `UpdateBanner` (non nel nativo).
  nginx: `sw.js`/manifest `expires -1` (un `add_header` in una location cancella gli header di sicurezza).
- **Layout app-like**: `viewport-fit=cover`, safe-area top nel Topbar, `h-dvh` in AppShell.
- **Gesture** (`lib/haptics.ts`, `components/ui/SwipeableRow.tsx`, `lib/usePullToRefresh.ts`, BottomSheet con
  maniglia trascinabile): swipe riga movimento (destra = conferma se `needs_review` e categoria presente, sinistra =
  apre dettaglio), pull-to-refresh su `<main>` (`overscroll-y-contain` blocca quello nativo di Chrome). Lo swipe NON
  elimina mai (DELETE e' definitivo). Non fatto: swipe tra periodi, long-press selezione.
- **Privacy importi**: `lib/privacy.ts` + remount di `AppRouter` come per la lingua; occhio nel Topbar. Copre solo i
  formattatori di `lib/format.ts` (formatMoney/Signed/Compact/Large), non quantita' ne' percentuali.
- **Backend nativo**: header `X-Lumio-Client: native` -> refresh token nel body (nessun cookie), CORS solo per
  `MOBILE_APP_ORIGINS` senza credenziali; `PATCH /transactions/{id}` accetta `needs_review: false`.
- **Guscio Android** (`frontend/android/`, `capacitor.config.ts`): androidScheme "http" + cleartext (cosi' si
  chiamano sia server https sia http in LAN; origin `http://localhost`), `allowBackup=false`, plugin locale
  `PrivacyScreenPlugin.java` (FLAG_SECURE), icone adaptive. Token nel Keystore (`lib/secureToken.ts`), biometria
  con fallback PIN (`lib/biometric.ts`), blocco app (`features/native/AppLockProvider.tsx`; a freddo i figli non
  sono montati finche' non si sblocca), pagina Impostazioni > App mobile.
- **Push**: tabella `push_devices` (migration 0046, RLS owner-only), `/push/*`, `services/push_service.py` (FCM
  HTTP v1 con PyJWT+httpx, no-op senza `FCM_SERVICE_ACCOUNT_FILE`), invio dopo sync bancaria SCHEDULATA con nuovi
  movimenti, testo senza importi.

## Verificato su telefono Android (2026-11-07, utente)
- Server di produzione aggiornato (migration 0044-0046, password Redis), APK di debug installato, login e blocco con
  impronta funzionanti. APK compilato da GitHub: workflow manuale `.github/workflows/android-apk.yml` (artefatto
  `lumio-debug-apk`); sul PC di sviluppo manca `gh` (Android Studio non serve: vedi build locale).
- Header sotto la barra di stato: risolto con `--sat`/`--sab` = max(env(), --safe-area-inset-*) (`styles/global.css`), verificato su telefono.
- Build locale senza Android Studio: JDK 21 + SDK cmdline-tools in `C:\Android`, script `frontend/scripts/build-apk.ps1 [-Install]`
  (guida in `docs/mobile-app.md`). Gradle/Java falliscono con "Unable to establish loopback connection" nella sandbox di
  Claude: la build va lanciata dal terminale dell'utente (`run_in_terminal`). Chiave di debug locale != GitHub: non si
  aggiornano a vicenda. `INSTALL_FAILED_USER_RESTRICTED` = serve confermare/abilitare "Installa tramite USB" sul telefono.
- Ancora da provare: swipe/pull-to-refresh nell'app, privacy screen (FLAG_SECURE), 2FA, push (serve Firebase).
- Dal LXC di produzione il dominio pubblico non e' raggiungibile (niente hairpin): i test dall'esterno vanno fatti da PC/telefono.

## Limiti / da sapere
- Open Banking e Google OAuth usano redirect del browser: dall'app nativa si fanno dal sito web.
- Biometria = gate applicativo sul Keystore (plugin aparajita), non chiave legata alla biometria.
- Push richiede `google-services.json` in `frontend/android/app/` (ignorato da git) e il service account sul server.
- Il package-lock.json e' cambiato molto (npm 11): normale, non e' un errore.

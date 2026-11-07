# App mobile (Android, iOS poi)

Lumio ha due modi di usarla da telefono:

1. **PWA**: apri l'indirizzo del tuo server in Chrome, menu → "Installa app". Stesso codice del sito.
2. **App nativa (Capacitor)**: lo stesso frontend React dentro un guscio Android. Alla prima apertura chiede
   l'indirizzo del tuo server. Aggiunge blocco con impronta/volto, haptics e notifiche push.

## Cosa serve per compilare l'APK
- Android Studio (include SDK e JDK) con un telefono in modalita' sviluppatore (o un emulatore).
- Da `frontend/`: `npm install`, poi `npm run android:sync` e `npm run android:open`.
- In Android Studio: **Run** sul telefono, oppure *Build → Generate Signed App Bundle / APK* per un APK da installare.

## Server
- Meglio HTTPS con dominio stabile. Con `http://` (LAN) l'app funziona ma avvisa se l'host e' pubblico.
- Il backend ammette l'origin dell'app (`MOBILE_APP_ORIGINS`, default gia' corretto) senza cookie: l'app usa un
  refresh token conservato nel Keystore di Android (header `X-Lumio-Client: native`).
- Il collegamento delle banche (Open Banking) e l'integrazione Google passano da redirect del browser: farli dal
  sito web, poi i dati sono gia' nell'app.

## Notifiche push (opzionali)
1. Console Firebase → nuovo progetto → aggiungi app Android con package `app.lumio.mobile`.
2. Scarica `google-services.json` e mettilo in `frontend/android/app/` (e' gia' ignorato da git: non committarlo). Ricompila l'APK.
3. Impostazioni progetto → Account di servizio → *Genera nuova chiave privata* (JSON).
4. Monta il JSON nel container (es. `./secrets/fcm.json:/run/secrets/fcm.json:ro` su `app` e `worker`) e imposta
   `FCM_SERVICE_ACCOUNT_FILE=/run/secrets/fcm.json` nel `.env`. Riavvia `app` e `worker`.
5. Nell'app: Impostazioni → App mobile → "Ricevi notifiche".
Le notifiche non contengono importi. Partono dopo una sync bancaria automatica con movimenti nuovi.

## Sicurezza
- Blocco app: impronta/volto o PIN del telefono; nasconde l'app nelle recenti e blocca gli screenshot.
- Il blocco protegge l'uso dell'app, non e' un secondo fattore sul server: per quello c'e' la 2FA (TOTP) in
  Impostazioni → Sicurezza.

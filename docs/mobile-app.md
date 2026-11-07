# App mobile (Android, iOS poi)

Lumio ha due modi di usarla da telefono:

1. **PWA**: apri l'indirizzo del tuo server in Chrome, menu → "Installa app". Stesso codice del sito.
2. **App nativa (Capacitor)**: lo stesso frontend React dentro un guscio Android. Alla prima apertura chiede
   l'indirizzo del tuo server. Aggiunge blocco con impronta/volto, haptics e notifiche push.

## Compilare l'APK

Due strade, con lo stesso risultato (APK di debug, installabile sul proprio telefono):

- **Locale** (sotto): senza Android Studio, in circa un minuto dopo la prima volta.
- **GitHub**: Actions → *Build APK Android* → Run workflow, poi scarichi l'artefatto `lumio-debug-apk`.

> Le due strade usano chiavi di debug diverse: un APK compilato in locale non si installa "sopra" uno compilato
> da GitHub (e viceversa). Se Android rifiuta l'aggiornamento, disinstalla prima l'app. Scegli una strada per telefono.

### Build locale senza Android Studio

**Cosa installare (una volta sola, in `C:\Android`, senza amministratore e senza toccare le variabili d'ambiente):**

| Cosa | Da dove | Dimensione |
|---|---|---|
| JDK 21 (Temurin), zip | `https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse` | ~200 MB |
| Android command-line tools, zip | `https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip` | ~150 MB |
| Componenti SDK: `platform-tools`, `platforms;android-36`, `build-tools;36.0.0` | `sdkmanager` (scaricati da Google, con accettazione delle licenze) | ~1 GB |
| Gradle 8.14 e librerie del progetto | scaricati dal wrapper alla prima build | ~500 MB |

Passi (PowerShell):

1. Estrai lo zip del JDK in `C:\Android\jdk-21` (la cartella deve contenere `bin\java.exe`).
2. Estrai lo zip delle command-line tools in `C:\Android\sdk\cmdline-tools\latest` (deve contenere `bin\sdkmanager.bat`).
3. Installa i componenti e accetta le licenze:
   ```powershell
   $env:JAVA_HOME = 'C:\Android\jdk-21'
   C:\Android\sdk\cmdline-tools\latest\bin\sdkmanager.bat --sdk_root=C:\Android\sdk --licenses
   C:\Android\sdk\cmdline-tools\latest\bin\sdkmanager.bat --sdk_root=C:\Android\sdk "platform-tools" "platforms;android-36" "build-tools;36.0.0"
   ```
4. Per installare direttamente sul telefono: sul telefono attiva *Opzioni sviluppatore* e *Debug USB*, collegalo con
   il cavo e accetta la richiesta di autorizzazione.

**Come si compila (da `frontend/`):**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-apk.ps1            # compila
powershell -ExecutionPolicy Bypass -File .\scripts\build-apk.ps1 -Install   # compila e installa sul telefono
```
L'APK esce in `frontend\android\app\build\outputs\apk\debug\app-debug.apk`. Lo script fa: build web, `cap sync`,
Gradle `assembleDebug` e, con `-Install`, `adb install -r`. Se gli strumenti sono altrove, usa `-ToolsRoot D:\percorso`
o la variabile `LUMIO_ANDROID_ROOT`.

**Problemi noti**
- `Unable to establish loopback connection` (Gradle/Java): succede solo in alcuni ambienti isolati (sandbox,
  alcuni strumenti di sicurezza). Dal terminale normale di Windows non si presenta.
- Android Studio non serve; se lo installi, `npm run android:open` lo apre sul progetto.

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

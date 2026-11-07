# Compila l'APK di debug di Lumio in locale, senza Android Studio.
#
# Uso (da frontend/):
#   .\scripts\build-apk.ps1            # compila
#   .\scripts\build-apk.ps1 -Install   # compila e installa sul telefono collegato (debug USB)
#
# Richiede gli strumenti in C:\Android (JDK 21 + Android SDK da riga di comando):
# vedi docs/mobile-app.md. Non modifica variabili d'ambiente o impostazioni di
# sistema: JAVA_HOME e ANDROID_HOME valgono solo per questo script.
param(
    [switch]$Install,
    [string]$ToolsRoot = $(if ($env:LUMIO_ANDROID_ROOT) { $env:LUMIO_ANDROID_ROOT } else { 'C:\Android' })
)

$ErrorActionPreference = 'Stop'
$frontend = Split-Path -Parent $PSScriptRoot
$jdk = Join-Path $ToolsRoot 'jdk-21'
$sdk = Join-Path $ToolsRoot 'sdk'

foreach ($required in @(
        @{ Path = (Join-Path $jdk 'bin\java.exe'); What = 'JDK 21' },
        @{ Path = (Join-Path $sdk 'platforms\android-36'); What = 'Android SDK (platforms;android-36)' },
        @{ Path = (Join-Path $sdk 'build-tools'); What = 'Android SDK (build-tools)' })) {
    if (-not (Test-Path $required.Path)) {
        throw "Manca $($required.What) in $($required.Path). Segui la sezione 'Build locale' di docs/mobile-app.md."
    }
}

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
# Gradle comunica tra i suoi processi via loopback: su Windows con IPv6 attivo puo'
# fallire con "Unable to establish loopback connection". Forzare IPv4 lo evita.
$env:JAVA_TOOL_OPTIONS = '-Djava.net.preferIPv4Stack=true'
$env:Path = "$jdk\bin;$sdk\platform-tools;$env:Path"

function Invoke-Step([string]$Title, [scriptblock]$Action) {
    Write-Host "`n== $Title" -ForegroundColor Cyan
    # Gli avvisi su stderr di npm/gradle non sono errori: conta solo il codice di uscita.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Action } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "Passo fallito: $Title (codice $LASTEXITCODE)" }
}

Push-Location $frontend
try {
    Invoke-Step 'Build web' { npm run build }
    Invoke-Step 'Sync Capacitor' { npx cap sync android }

    # local.properties e' ignorato da git: dice a Gradle dov'e' l'SDK.
    $sdkForGradle = $sdk -replace '\\', '/'
    Set-Content -Path (Join-Path $frontend 'android\local.properties') -Value "sdk.dir=$sdkForGradle" -Encoding ascii

    Push-Location (Join-Path $frontend 'android')
    try {
        Invoke-Step 'Compila APK di debug (la prima volta scarica Gradle e le librerie: alcuni minuti)' {
            .\gradlew.bat assembleDebug --no-daemon
        }
    } finally { Pop-Location }

    $apk = Join-Path $frontend 'android\app\build\outputs\apk\debug\app-debug.apk'
    if (-not (Test-Path $apk)) { throw "APK non trovato: $apk" }
    Write-Host "`nAPK pronto: $apk" -ForegroundColor Green

    if ($Install) {
        Invoke-Step 'Installazione sul telefono' {
            $adb = Join-Path $sdk 'platform-tools\adb.exe'
            $devices = (& $adb devices) | Select-String -Pattern "`tdevice$"
            if (-not $devices) { throw "Nessun telefono collegato: attiva 'Debug USB' e accetta la richiesta sul telefono." }
            & $adb install -r $apk
        }
    }
} finally { Pop-Location }

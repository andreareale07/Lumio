from functools import lru_cache

from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_KEY_MIN_LENGTH = 32
# Frammenti dei valori di esempio: se il valore li contiene e' quello copiato
# da `.env.example`, quindi noto a chiunque.
_SECRET_KEY_PLACEHOLDERS = ("change-me", "changeme", "ci-secret-key", "secret")
_OPEN_BANKING_HOSTS = ("api.enablebanking.com",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Lumio"
    app_tagline: str = "See your money clearly."
    app_env: str = "development"

    database_url: str
    redis_url: str

    secret_key: str
    storage_path: str = "/app/storage"

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # --- AI Abstraction (milestone 07) ---
    # Ogni workspace configura i propri profili AI via `/settings/ai`
    # (piu' profili salvabili, uno attivo per volta) — nessun default
    # d'istanza da `.env`: a differenza della prima versione di questa
    # milestone (un'unica riga per workspace), un profilo ha anche un
    # `name` scelto dall'utente, che non ha senso pre-generare da env var.
    # 30s era tarato su provider cloud: con un modello locale (Ollama su
    # GPU low-power) il prefill del prompt (few-shot + ~70-80 categorie)
    # da solo puo' avvicinarsi a quella soglia, facendo scattare il timeout
    # come "provider non raggiungibile" prima che l'inferenza finisca
    # davvero (vedi ai/providers/ollama.py: stesso errore per
    # irraggiungibilita' reale e per timeout, entrambi httpx.HTTPError).
    ai_classify_timeout_seconds: int = 120
    ai_test_timeout_seconds: int = 10
    # Rework pipeline: quante chiamate al provider tenere in volo
    # contemporaneamente durante la classificazione di un import (job
    # separato, vedi ai_classification_job.py). Ollama locale serializza
    # comunque sulla GPU: alzare la concorrenza li' non guadagna nulla e
    # rischia solo di saturare il processo, quindi resta fissa a 1
    # indipendentemente da questo valore (vedi ai_classification_job.py).
    ai_max_concurrency: int = 4
    # Retry con backoff esponenziale su 429 (rate limit)/5xx dei provider
    # cloud (OpenAI/Anthropic/Custom) — oggi assenti del tutto, un
    # rate-limit temporaneo falliva l'intera riga invece di essere
    # ritentato. Non usato da Ollama (locale, non ha un concetto di
    # rate-limit cloud; i suoi errori sono quasi sempre di connessione,
    # gia' gestiti come AIProviderError immediato).
    ai_max_retries: int = 2

    google_enabled: bool = False
    # Secret di ISTANZA (non di workspace): un solo OAuth client Google per
    # l'intera installazione self-hosted, creato dall'operatore su Google
    # Cloud Console. Letti solo se google_enabled=True (validati al primo
    # uso da app/integrations/google/oauth.py, non a startup, per non
    # rompere l'avvio quando l'integrazione resta disabilitata).
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    # Browser key ristretta alla Picker API (diversa dal client OAuth sopra)
    # per il widget Google Picker lato frontend (selezione cartella Drive).
    google_picker_api_key: str = ""
    google_export_job_timeout_seconds: int = 120

    # --- Open Banking (connettore Enable Banking) ---
    # Opzionale come Google: con False nessun endpoint esiste (404) e l'app
    # funziona al 100% con import PDF/CSV. Nessuna credenziale d'istanza:
    # l'application ID e la chiave privata sono per UTENTE (i Terms di Enable
    # Banking permettono la produzione gratuita solo per uso personale con
    # conti propri, mai credenziali condivise), salvate cifrate nel DB.
    open_banking_enabled: bool = False
    # URL pubblico (HTTPS) del callback, da registrare identico nel Control
    # Panel di Enable Banking: https://<dominio>/api/v1/open-banking/callback
    open_banking_redirect_uri: str = ""
    open_banking_base_url: str = "https://api.enablebanking.com"
    # Solo per chi ha un accordo con indirizzi diversi: in produzione la base URL
    # e' limitata a Enable Banking (vedi `_check_production_security`).
    open_banking_allow_custom_base_url: bool = False
    open_banking_http_timeout_seconds: float = 30.0
    # Intervallo minimo tra due sincronizzazioni automatiche della stessa
    # connessione. Molte banche limitano a 4 accessi al giorno senza l'utente
    # presente: sotto le 6 ore il valore viene riportato a 6 (vedi
    # bank_sync_service.effective_interval_seconds).
    open_banking_sync_interval_hours: int = 8
    # Finestra di riconciliazione: ogni sync riparte da questi giorni prima
    # dell'ultimo movimento importato, per recepire contabilizzazioni tardive.
    open_banking_reconcile_days: int = 7
    open_banking_sync_job_timeout_seconds: int = 900

    @model_validator(mode="after")
    def _check_production_security(self) -> "Settings":
        """Con `APP_ENV=production` l'app non parte con una configurazione che
        renderebbe inutile la cifratura: `SECRET_KEY` firma i JWT e deriva la
        chiave che protegge le chiavi bancarie e le API key nel DB."""
        if self.app_env != "production":
            return self
        key = self.secret_key.strip().lower()
        if len(key) < _SECRET_KEY_MIN_LENGTH or any(p in key for p in _SECRET_KEY_PLACEHOLDERS):
            raise ValueError(
                "SECRET_KEY non sicuro per APP_ENV=production: servono almeno "
                f"{_SECRET_KEY_MIN_LENGTH} caratteri casuali e non il valore di esempio "
                "(genera: python -c \"import secrets; print(secrets.token_urlsafe(64))\"). "
                "Attenzione: cambiare la chiave dopo il primo avvio rende illeggibili "
                "i segreti gia' cifrati (chiavi bancarie, API key AI)."
            )
        if self.open_banking_enabled and self.open_banking_redirect_uri:
            if not self.open_banking_redirect_uri.startswith("https://"):
                raise ValueError("OPEN_BANKING_REDIRECT_URI deve essere HTTPS in produzione")
        if not self.open_banking_base_url.startswith("https://"):
            raise ValueError("OPEN_BANKING_BASE_URL deve essere HTTPS in produzione")
        # L'API firmata con la tua chiave privata va solo a Enable Banking: un
        # indirizzo diverso (variabile manomessa) riceverebbe i JWT firmati.
        host = (urlsplit(self.open_banking_base_url).hostname or "").lower()
        if not self.open_banking_allow_custom_base_url and host not in _OPEN_BANKING_HOSTS:
            raise ValueError(
                "OPEN_BANKING_BASE_URL non e' un host di Enable Banking: se e' voluto "
                "imposta OPEN_BANKING_ALLOW_CUSTOM_BASE_URL=true"
            )
        return self

    # --- Riclassificazione (rework pipeline di classificazione) ---
    # Puo' scorrere l'intero storico di un workspace (potenzialmente
    # migliaia di righe, N chiamate AI se run_ai=True): budget ampio come
    # ai_classification_job_timeout_seconds, non quello piu' stretto di un
    # singolo import.
    reclassification_job_timeout_seconds: int = 10800
    positions_recompute_job_timeout_seconds: int = 1800

    # --- Import Engine (milestone 04) ---
    max_import_file_size_bytes: int = 10 * 1024 * 1024
    import_job_timeout_seconds: int = 300
    job_events_ttl_seconds: int = 86400
    # Classificazione AI disaccoppiata dal job di import (rework UX/design):
    # budget proprio, molto piu' ampio di import_job_timeout_seconds — deve
    # coprire N chiamate sequenziali al provider (~ai_classify_timeout_seconds
    # ciascuna), non solo una singola chiamata. 1800s (30min) si e' rivelato
    # troppo stretto su dati reali: un import da 83 transazioni con un
    # modello locale leggero (gemma3:1b) ha classificato 46/83 in 30 minuti
    # (~39s/chiamata col prompt completo, non un caso patologico) prima di
    # essere interrotto da QUESTO timeout — zero errori di provider, il job
    # stava semplicemente ancora lavorando. 3 ore da margine per import piu'
    # grandi senza pretendere di aver gia' misurato il caso peggiore reale.
    ai_classification_job_timeout_seconds: int = 10800

    # --- Trade Republic Parser / import PDF (milestone 05) ---
    # Limite piu' stretto del job_timeout generale (SPEC §53): l'apertura di
    # verifica gira in-request durante l'upload (stesso schema di
    # detect_mapping per il CSV), quindi deve fallire rapidamente su un PDF
    # patologico invece di tenere la richiesta HTTP appesa fino al timeout
    # lungo pensato per il worker.
    import_pdf_open_timeout_seconds: int = 10
    import_pdf_parse_timeout_seconds: int = 60

    # --- Storico patrimonio ricostruito (FETTA 3 di
    # docs/PLAN_TAXONOMY_I18N.md / rework Spese-Entrate-Dashboard) ---
    # Clamp sull'inizio del backfill: una data digitata male (o un
    # `period_start` corrotto) non deve generare decine di migliaia di
    # righe. Quando il clamp scatta, il job lo dichiara in `run.message`,
    # mai un troncamento silenzioso.
    snapshot_backfill_max_years: int = 10
    # Dominato dalla fase prezzi (chiamate HTTP per asset posseduto + FX
    # all'indietro), non dalla matematica del calcolo — stesso ordine di
    # grandezza di reclassification_job_timeout_seconds/
    # ai_classification_job_timeout_seconds.
    snapshot_backfill_job_timeout_seconds: int = 10800
    # Rate limiting fra un asset/valuta e il successivo durante il backfill
    # storico (Yahoo risponde 429/999 senza, vedi marketdata/providers/
    # yahoo.py) — non usato dal refresh quotidiano (worker/jobs/market_data.py),
    # solo dal backfill che scarica molte piu' chiamate in sequenza in un
    # colpo solo.
    market_data_backfill_delay_seconds: float = 0.5

    # --- Fiscalita' conti titoli (SPEC_TAX_REGIME.md, FETTA 1) ---
    # Giurisdizione usata quando il workspace non ha ancora dichiarato la
    # propria residenza fiscale per l'anno richiesto — la response propaga
    # `residence_declared=False` fino alla UI, mai un default silenzioso.
    tax_default_jurisdiction: str = "IT"


@lru_cache
def get_settings() -> Settings:
    return Settings()

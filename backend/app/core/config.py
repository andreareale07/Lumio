from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- Riclassificazione (rework pipeline di classificazione) ---
    # Puo' scorrere l'intero storico di un workspace (potenzialmente
    # migliaia di righe, N chiamate AI se run_ai=True): budget ampio come
    # ai_classification_job_timeout_seconds, non quello piu' stretto di un
    # singolo import.
    reclassification_job_timeout_seconds: int = 10800

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


@lru_cache
def get_settings() -> Settings:
    return Settings()

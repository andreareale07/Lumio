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
    ai_classify_timeout_seconds: int = 30
    ai_test_timeout_seconds: int = 10

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

    # --- Import Engine (milestone 04) ---
    max_import_file_size_bytes: int = 10 * 1024 * 1024
    import_job_timeout_seconds: int = 300
    job_events_ttl_seconds: int = 86400
    # Classificazione AI disaccoppiata dal job di import (rework UX/design):
    # budget proprio, molto piu' ampio di import_job_timeout_seconds — deve
    # coprire N chiamate sequenziali al provider (~ai_classify_timeout_seconds
    # ciascuna), non solo una singola chiamata.
    ai_classification_job_timeout_seconds: int = 1800

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

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

    ai_provider: str = "none"
    ai_endpoint: str = ""
    ai_model: str = ""

    google_enabled: bool = False

    # --- Import Engine (milestone 04) ---
    max_import_file_size_bytes: int = 10 * 1024 * 1024
    import_job_timeout_seconds: int = 300
    job_events_ttl_seconds: int = 86400

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

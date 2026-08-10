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

    ai_provider: str = "none"
    ai_endpoint: str = ""
    ai_model: str = ""

    google_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Settings from environment variables, so one image runs locally, in Compose and on Cloud Run."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_NAME = "engine"
DEFAULT_PORT = 8084


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = SERVICE_NAME
    app_version: str = "dev"
    port: int = DEFAULT_PORT
    log_level: str = "INFO"
    log_json: bool = True
    # All Telstra calls go through telstra-gateway, never straight to Telstra.
    gateway_url: str = "http://localhost:8082"
    # Postgres, engine schema (incidents and verdicts). Empty = run without a database.
    database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

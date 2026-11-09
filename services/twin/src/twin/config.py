"""Settings from environment variables, so one image runs locally, in Compose and on Cloud Run."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_NAME = "twin"
DEFAULT_PORT = 8085


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = SERVICE_NAME
    app_version: str = "dev"
    port: int = DEFAULT_PORT
    log_level: str = "INFO"
    log_json: bool = True
    # Where the twin sends what it simulates.
    telstra_fake_url: str = "http://localhost:8083"
    ingest_url: str = "http://localhost:8081"
    seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()

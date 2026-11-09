"""Settings from environment variables, so one image runs locally, in Compose and on Cloud Run."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_NAME = "service-template"
DEFAULT_PORT = 8080


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = SERVICE_NAME
    app_version: str = "dev"
    port: int = DEFAULT_PORT
    log_level: str = "INFO"
    log_json: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

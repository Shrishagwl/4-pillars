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
    # Optional Gemini summaries (see summary.py). Off = the built-in template is used.
    llm_summary: bool = False
    gcp_project: str = ""
    gcp_location: str = "australia-southeast1"
    gemini_model: str = "gemini-2.5-flash"
    # Where the meter list comes from (ingest-api owns it). Empty = no live service.
    ingest_url: str = ""
    # "v1" rules or "v2" learned model (MODEL_PATH points at its model.json).
    scorer: str = "v1"
    model_path: str = ""
    # Re-score this often even with no new events: incidents change as time passes.
    tick_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

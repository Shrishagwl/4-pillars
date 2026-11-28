import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from . import db
from .config import Settings, get_settings
from .logging import setup_logging

log = logging.getLogger(__name__)


class Health(BaseModel):
    status: str = "ok"
    service: str
    version: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(
        settings.log_level, settings.service_name, settings.app_version, settings.log_json
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Bring the schema up to date before taking traffic. Safe to run on every start.
        if settings.database_url:
            with db.connect(settings.database_url) as conn:
                applied = db.migrate(conn)
            log.info(
                "migrations applied" if applied else "schema up to date", extra={"applied": applied}
            )
        else:
            log.warning("DATABASE_URL is not set: running without a database")
        yield

    app = FastAPI(title=settings.service_name, version=settings.app_version, lifespan=lifespan)

    @app.get("/health", response_model=Health)
    def health() -> Health:
        return Health(service=settings.service_name, version=settings.app_version)

    # Add this service's routers here: app.include_router(...)
    log.info("app created", extra={"port": settings.port})
    return app


app = create_app()

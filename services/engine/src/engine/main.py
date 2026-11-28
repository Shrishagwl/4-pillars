import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path

import httpx2
from fastapi import FastAPI
from pydantic import BaseModel

from . import db
from .bayes import NaiveBayes
from .config import Settings, get_settings
from .gateway import Gateway, _cloud_run_token
from .logging import setup_logging
from .receiver import EventSink, LoggingSink, make_router
from .rules import score_v1
from .service import EngineService, utc_now
from .store import EngineStore
from .summary import generator_from_settings
from .topology import Meter

log = logging.getLogger(__name__)


class Health(BaseModel):
    status: str = "ok"
    service: str
    version: str


def meters_from_ingest(ingest_url: str):
    """Load the meter list from ingest-api, which owns it."""
    base = ingest_url.rstrip("/")

    def load() -> list[Meter]:
        res = httpx2.get(f"{base}/meters", headers=_cloud_run_token(base), timeout=10)
        res.raise_for_status()
        return [
            Meter(
                m["meterId"],
                m["msisdn"],
                m["transformerId"],
                m["suburb"],
                m["postcode"],
                m.get("state") or "VIC",
                m.get("lat"),
                m.get("lon"),
            )  # fmt: skip
            for m in res.json()["meters"]
        ]

    return load


def scorer_from_settings(settings: Settings):
    if settings.scorer == "v2":
        model = NaiveBayes.load(Path(settings.model_path))
        return model.score
    return score_v1


def create_app(settings: Settings | None = None, sink: EventSink | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(
        settings.log_level, settings.service_name, settings.app_version, settings.log_json
    )
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bring the schema up to date before taking traffic. Safe to run on every start.
        store = None
        if settings.database_url:
            with db.connect(settings.database_url) as conn:
                applied = db.migrate(conn)
            log.info(
                "migrations applied" if applied else "schema up to date", extra={"applied": applied}
            )
            state["conn"] = db.connect(settings.database_url)
            store = EngineStore(state["conn"])
        else:
            log.warning("DATABASE_URL is not set: running without a database")

        ticker = None
        if sink is None and settings.ingest_url:
            service = EngineService(
                meters_from_ingest(settings.ingest_url),
                store=store,
                gateway=Gateway(settings.gateway_url) if settings.gateway_url else None,
                scorer=scorer_from_settings(settings),
                generate=generator_from_settings(settings),
            )
            await asyncio.to_thread(service.rebuild)
            app.state.sink = service
            app.state.service = service
            app.state.store = store

            async def tick_forever():
                while True:
                    await asyncio.sleep(settings.tick_seconds)
                    try:
                        await asyncio.to_thread(service.tick)
                    except Exception:  # noqa: BLE001  (one bad tick must not stop the loop)
                        log.exception("tick failed")

            ticker = asyncio.create_task(tick_forever())
        yield
        if ticker:
            ticker.cancel()
            with suppress(asyncio.CancelledError):
                await ticker
        if "conn" in state:
            state["conn"].close()

    app = FastAPI(title=settings.service_name, version=settings.app_version, lifespan=lifespan)
    app.state.sink = sink or LoggingSink()
    app.state.service = None
    app.state.store = None

    @app.get("/health", response_model=Health)
    def health() -> Health:
        return Health(service=settings.service_name, version=settings.app_version)

    @app.get("/incidents")
    def incidents(closed_within_minutes: int = 60) -> dict:
        """Newest verdict of every open incident, plus ones closed recently. ingest-api turns
        this into the dashboard's Incident shape (#29)."""
        if app.state.store is not None:
            since = utc_now() - timedelta(minutes=closed_within_minutes)
            return {"incidents": app.state.store.latest_verdicts(since)}
        service = app.state.service
        now = utc_now()
        items = []
        for incident in service.incidents if service else []:
            v = incident.verdict(now)
            cluster = incident.assessment.cluster
            items.append(
                {
                    **v.model_dump(mode="json"),
                    "openedAt": cluster.members[0].silent_at.isoformat(),
                    "closedAt": None,
                    "meterIds": sorted(incident.meter_ids),
                    "transformerIds": sorted(cluster.transformer_ids),
                    "suburbs": sorted(cluster.suburbs),
                }
            )
        return {"incidents": items}

    # The receiver looks the sink up on every request, so the service built at startup is used.
    app.include_router(make_router(_SinkProxy(app)))
    log.info("app created", extra={"port": settings.port})
    return app


class _SinkProxy:
    def __init__(self, app: FastAPI) -> None:
        self._app = app

    def accept(self, events) -> None:
        self._app.state.sink.accept(events)


app = create_app()

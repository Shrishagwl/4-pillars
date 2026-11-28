import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .clock import DEFAULT_START
from .config import Settings, get_settings
from .logging import setup_logging
from .run import run_scenario
from .scenario import RANDOM, ScenarioError, load_scenario, parse_scenario
from .service import Player, Status

log = logging.getLogger(__name__)

FAULT_TARGET = {"power": "transformer", "network": "suburb", "meter": "meter", "tamper": "meter"}


class Health(BaseModel):
    status: str = "ok"
    service: str
    version: str


class StartScenario(BaseModel):
    """Either a scenario file by name (scenarios/<name>.yaml) or a whole scenario inline."""

    name: str | None = None
    scenario: dict | None = None
    seed: int = 1


class InjectFault(BaseModel):
    """One fault, starting now. Same shape as the evaluation's runs: the fault comes a minute in
    and the run lasts half an hour after it."""

    kind: Literal["power", "network", "meter", "tamper"]
    target: str = RANDOM
    seed: int = 1
    blips_per_hour: float = Field(default=0, ge=0, le=60)


def create_app(settings: Settings | None = None, player: Player | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(
        settings.log_level, settings.service_name, settings.app_version, settings.log_json
    )
    app = FastAPI(title=settings.service_name, version=settings.app_version)
    app.state.player = player or Player(
        settings.telstra_fake_url, settings.ingest_url, settings.ingest_api_key
    )

    @app.get("/health", response_model=Health)
    def health() -> Health:
        return Health(service=settings.service_name, version=settings.app_version)

    def start(scenario, seed: int) -> Status:
        player: Player = app.state.player
        if player.busy:
            raise HTTPException(409, "a scenario is already playing; POST /scenarios/stop first")
        result = run_scenario(scenario, seed)
        status = player.start(result, DEFAULT_START)
        log.info("scenario started", extra={"scenario": scenario.name, "seed": seed})
        return status

    @app.post("/scenarios", status_code=202)
    def start_scenario(body: StartScenario) -> Status:
        try:
            if body.name:
                path = Path(settings.scenarios_dir) / f"{body.name}.yaml"
                if not path.is_file():
                    raise HTTPException(404, f"no scenario called {body.name!r}")
                scenario = load_scenario(path)
            elif body.scenario is not None:
                scenario = parse_scenario(body.scenario, source="request")
            else:
                raise HTTPException(400, "send a scenario name or a scenario")
        except ScenarioError as err:
            raise HTTPException(400, str(err)) from err
        return start(scenario, body.seed)

    @app.post("/faults", status_code=202)
    def inject_fault(body: InjectFault) -> Status:
        data: dict = {
            "name": f"live-{body.kind}",
            "duration_min": 31,
            "faults": [{"kind": body.kind, "at_min": 1, FAULT_TARGET[body.kind]: body.target}],
        }
        if body.blips_per_hour:
            data["noise"] = {"dropouts_per_hour": body.blips_per_hour}
        try:
            scenario = parse_scenario(data, source="request")
        except ScenarioError as err:
            raise HTTPException(400, str(err)) from err
        return start(scenario, body.seed)

    @app.get("/scenarios/current")
    def current() -> Status:
        return app.state.player.status

    @app.post("/scenarios/stop")
    def stop() -> Status:
        return app.state.player.stop()

    @app.get("/scenarios")
    def names() -> dict[str, list[str]]:
        return {"scenarios": sorted(p.stem for p in Path(settings.scenarios_dir).glob("*.yaml"))}

    log.info("app created", extra={"port": settings.port})
    return app


app = create_app()

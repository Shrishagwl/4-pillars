"""The twin as a running service (#35): play a scenario live into telstra-fake and ingest-api.

A scenario run (run.py) is worked out in full first, exactly as the evaluation does it, so the
live run and the library run see the same events. Then it is played on the wall clock:

  - scenario time is shifted so the first fault happens "now". Anything before that (background
    blips in the first minutes) is sent straight away, with its real past timestamps.
  - each LoC report goes to telstra-fake at its time, and the fake calls ingest-api back
  - each network outage is added to the fake's Network Availability when Telstra would list it
  - each tampered SIM is moved in the fake's Location Verification when it turns up elsewhere

Before playing, the twin registers its meters with ingest-api, subscribes every SIM to Loss of
Connectivity on the fake (callback: ingest-api), and puts every SIM at its meter's address.
"""

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx2

from .grid import Twin, build_twin
from .run import RunResult

log = logging.getLogger(__name__)

METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)
CALLBACK_PATH = "/loss-of-connectivity/v0/events"
TELSTRA_HEADERS = {  # the fake checks these like Telstra does
    "authorization": "Bearer twin",
    "correlation-id": "550e8400-e29b-41d4-a716-446655440000",
}


def _cloud_run_auth(url: str) -> dict[str, str]:
    """Our Cloud Run services are private; on Cloud Run, get an ID token for the target.
    Sent in X-Serverless-Authorization so the Authorization header stays free."""
    if not os.environ.get("K_SERVICE") or ".run.app" not in url:
        return {}
    origin = "/".join(url.split("/")[:3])
    res = httpx2.get(
        METADATA_URL, params={"audience": origin}, headers={"Metadata-Flavor": "Google"}
    )
    res.raise_for_status()
    return {"x-serverless-authorization": f"Bearer {res.text}"}


@dataclass(order=True)
class Step:
    at: datetime
    what: str = field(compare=False)  # "loc", "outage", "move"
    payload: dict = field(compare=False)


def plan(result: RunResult, shift: timedelta) -> list[Step]:
    """Everything to send, in time order, already moved onto the wall clock."""
    steps = [
        Step(r.event_time + shift, "loc", {
            "msisdn": r.msisdn,
            "lossOfConnectReason": r.reason_code,
            "eventTime": (r.event_time + shift).isoformat(),
        })
        for r in result.loc_reports
    ]  # fmt: skip
    for o in result.outages:
        steps.append(
            Step(o.listed_at + shift, "outage", {
                "state": "VIC",
                "suburb": o.suburb,
                "postcode": o.postcode,
                "start": (o.started_at + shift).isoformat(),
                **({"end": (o.restored_at + shift).isoformat()} if o.restored_at else {}),
            })
        )  # fmt: skip
    for m in result.relocations:
        steps.append(
            Step(m.moved_at + shift, "move", {
                "phoneNumber": f"+{m.msisdn}",
                "latitude": m.lat,
                "longitude": m.lon,
                "locatedAt": (m.moved_at + shift).isoformat(),
            })
        )  # fmt: skip
    return sorted(steps)


def shift_for(result: RunResult, run_start: datetime, now: datetime) -> timedelta:
    """How far to move scenario time so the first fault starts now (or the run starts now if
    there is no fault)."""
    first = min((i.started_at for i in result.answer_key), default=run_start)
    return now - first


@dataclass
class Status:
    state: str = "idle"  # idle, preparing, playing, finished, stopped, failed
    scenario: str | None = None
    seed: int | None = None
    started_at: str | None = None
    fault_at: str | None = None
    sent: int = 0
    total: int = 0
    error: str | None = None
    answer_key: list[dict] = field(default_factory=list)


class Player:
    """Plays one run at a time in a background thread."""

    def __init__(
        self,
        fake_url: str,
        ingest_url: str,
        ingest_api_key: str = "",
        client: httpx2.Client | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        auth: Callable[[str], dict[str, str]] = _cloud_run_auth,
    ) -> None:
        self._fake = fake_url.rstrip("/")
        self._ingest = ingest_url.rstrip("/")
        self._key = ingest_api_key
        self._http = client or httpx2.Client(timeout=30)
        self._clock = clock
        self._sleep = sleep
        self._auth = auth
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = Status()

    # --- helpers

    def _post(self, url: str, body: dict, headers: dict | None = None, method: str = "POST"):
        res = self._http.request(
            method, url, json=body, headers={**self._auth(url), **(headers or {})}
        )
        res.raise_for_status()
        return res

    def prepare(self, twin: Twin) -> None:
        """Tell ingest-api and the fake about every meter."""
        meters = [
            {
                "meterId": m.meter_id,
                "msisdn": m.msisdn,
                "transformerId": m.transformer_id,
                "suburb": m.suburb,
                "postcode": m.postcode,
                "state": "VIC",
                "lat": m.lat,
                "lon": m.lon,
            }
            for m in twin.meters
        ]
        key = {"x-api-key": self._key} if self._key else {}
        self._post(f"{self._ingest}/meters", {"meters": meters}, key, method="PUT")
        # Subscribing a SIM twice is fine: the fake answers 207 SUBSCRIPTION_EXISTS.
        for i in range(0, len(meters), 500):
            chunk = [m["msisdn"] for m in meters[i : i + 500]]
            body = {
                "monitoringType": "LOSS_OF_CONNECTIVITY",
                "subscriptions": [
                    {"msisdn": chunk, "notificationDestination": self._ingest + CALLBACK_PATH}
                ],
            }
            self._post(f"{self._fake}/loss-of-connectivity/v0/subscriptions", body, TELSTRA_HEADERS)
        now = self._clock().isoformat()
        devices = [
            {
                "phoneNumber": f"+{m['msisdn']}",
                "latitude": m["lat"],
                "longitude": m["lon"],
                "locatedAt": now,
            }
            for m in meters
        ]
        self._post(f"{self._fake}/fake/location-verification/devices", {"devices": devices})

    def send(self, step: Step) -> None:
        if step.what == "loc":
            self._post(f"{self._fake}/fake/loss-of-connectivity/events", step.payload)
        elif step.what == "outage":
            self._post(f"{self._fake}/fake/network-availability/outages", step.payload)
        elif step.what == "move":
            self._post(f"{self._fake}/fake/location-verification/devices", step.payload)

    # --- running

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, result: RunResult, run_start: datetime) -> Status:
        if self.busy:
            raise RuntimeError("a scenario is already playing; stop it first")
        now = self._clock()
        shift = shift_for(result, run_start, now)
        steps = plan(result, shift)
        self.status = Status(
            state="preparing",
            scenario=result.scenario,
            seed=result.seed,
            started_at=now.isoformat(),
            fault_at=(
                min((i.started_at for i in result.answer_key), default=run_start) + shift
            ).isoformat(),
            total=len(steps),
            answer_key=[
                {
                    "cause": i.cause.value,
                    "target": i.target,
                    "startedAt": (i.started_at + shift).isoformat(),
                    "meterIds": list(i.meter_ids),
                }
                for i in result.answer_key
            ],
        )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._play, args=(build_twin(result.twin_seed), steps), daemon=True
        )
        self._thread.start()
        return self.status

    def _play(self, twin: Twin, steps: list[Step]) -> None:
        try:
            self.prepare(twin)
            self.status.state = "playing"
            for step in steps:
                wait = (step.at - self._clock()).total_seconds()
                while wait > 0 and not self._stop.is_set():
                    self._sleep(min(wait, 1.0))
                    wait = (step.at - self._clock()).total_seconds()
                if self._stop.is_set():
                    self.status.state = "stopped"
                    return
                self.send(step)
                self.status.sent += 1
            self.status.state = "finished"
            log.info(
                "scenario finished",
                extra={"scenario": self.status.scenario, "sent": self.status.sent},
            )
        except Exception as err:  # noqa: BLE001  (report it on /scenarios/current)
            log.exception("scenario failed")
            self.status.state = "failed"
            self.status.error = str(err)

    def stop(self) -> Status:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self.status.state in {"preparing", "playing"}:
            self.status.state = "stopped"
        return self.status

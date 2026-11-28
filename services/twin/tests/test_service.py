import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
from fastapi.testclient import TestClient

from twin.clock import DEFAULT_START
from twin.config import Settings
from twin.main import create_app
from twin.run import run_scenario
from twin.scenario import load_scenario
from twin.service import Player, plan, shift_for

SCENARIOS = Path(__file__).parents[1] / "scenarios"
NOW = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)


class FakeTime:
    """A clock that only moves when the player sleeps, so a 30-minute run takes no time."""

    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class FakeServices:
    """Records what the twin sends to telstra-fake and ingest-api."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.calls.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        return httpx2.Response(200, json={})

    def sent(self, path):
        return [body for _, p, body in self.calls if p == path]


def player(services, time):
    client = httpx2.Client(transport=httpx2.MockTransport(services))
    return Player(
        "http://fake:8083", "http://ingest:8081", "k3y",
        client=client, clock=time, sleep=time.sleep, auth=lambda _: {},
    )  # fmt: skip


def test_the_first_fault_is_moved_to_now_and_spacing_is_kept():
    result = run_scenario(load_scenario(SCENARIOS / "power-outage.yaml"), 1)
    shift = shift_for(result, DEFAULT_START, NOW)
    steps = plan(result, shift)
    assert result.answer_key[0].started_at + shift == NOW
    reports = sorted(result.loc_reports, key=lambda r: r.event_time)
    gaps = [(b.event_time - a.event_time) for a, b in zip(reports, reports[1:], strict=False)]
    live = [s for s in steps if s.what == "loc"]
    assert [(b.at - a.at) for a, b in zip(live, live[1:], strict=False)] == gaps
    assert live[0].payload["eventTime"] == (reports[0].event_time + shift).isoformat()


def test_a_power_cut_is_played_live_into_the_fake():
    services, time = FakeServices(), FakeTime()
    p = player(services, time)
    result = run_scenario(load_scenario(SCENARIOS / "power-outage.yaml"), 1)
    p.start(result, DEFAULT_START)
    p._thread.join(timeout=30)
    assert p.status.state == "finished"
    assert p.status.sent == len(result.loc_reports)

    # Set-up first: meters to ingest (with the key), SIMs subscribed, SIMs placed.
    first = services.calls[0]
    assert first[:2] == ("PUT", "/meters") and len(first[2]["meters"]) == 1730
    subs = services.sent("/loss-of-connectivity/v0/subscriptions")
    assert subs[0]["subscriptions"][0]["notificationDestination"] == (
        "http://ingest:8081/loss-of-connectivity/v0/events"
    )
    assert sum(len(s["subscriptions"][0]["msisdn"]) for s in subs) == 1730
    # Then every LoC report, at its shifted time.
    events = services.sent("/fake/loss-of-connectivity/events")
    assert len(events) == len(result.loc_reports)
    assert events[0]["eventTime"].startswith("2026-11-28T10:00")


def test_network_outages_and_tamper_moves_are_sent_too():
    services, time = FakeServices(), FakeTime()
    p = player(services, time)
    network = run_scenario(load_scenario(SCENARIOS / "network-outage.yaml"), 1)
    p.start(network, DEFAULT_START)
    p._thread.join(timeout=30)
    outages = services.sent("/fake/network-availability/outages")
    assert len(outages) == len(network.outages) >= 1
    assert outages[0]["state"] == "VIC" and outages[0]["postcode"]

    services.calls.clear()
    tamper = run_scenario(load_scenario(SCENARIOS / "tamper.yaml"), 0)
    p.start(tamper, DEFAULT_START)
    p._thread.join(timeout=30)
    moves = [b for b in services.sent("/fake/location-verification/devices") if "phoneNumber" in b]
    assert len(moves) == len(tamper.relocations)


def test_api_starts_a_fault_reports_status_and_stops():
    services, time = FakeServices(), FakeTime()
    p = player(services, time)
    client = TestClient(create_app(Settings(log_json=False, scenarios_dir=str(SCENARIOS)), p))
    assert "power-outage" in client.get("/scenarios").json()["scenarios"]

    res = client.post("/faults", json={"kind": "power", "seed": 3})
    assert res.status_code == 202
    assert res.json()["answer_key"][0]["cause"] == "POWER"
    p._thread.join(timeout=30)
    assert client.get("/scenarios/current").json()["state"] == "finished"

    assert client.post("/scenarios", json={"name": "nope"}).status_code == 404
    assert client.post("/scenarios", json={"scenario": {"name": "x"}}).status_code == 400
    assert client.post("/scenarios", json={"name": "quiet", "seed": 2}).status_code == 202
    p._thread.join(timeout=30)
    assert client.post("/scenarios/stop").json()["state"] in {"finished", "stopped"}

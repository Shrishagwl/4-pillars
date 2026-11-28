import os
import uuid
from datetime import timedelta

import httpx2
import psycopg
import pytest
from test_gateway import FakeGateway
from test_pipeline import METERS, NOW, network_outage_in_carlton, power_outage_on

from engine import db
from engine.contracts import Cause
from engine.gateway import Gateway
from engine.service import EngineService
from engine.store import EngineStore
from engine.topology import Meter


def with_uuids(events):
    """The DB keys events by UUID; the pipeline helpers use readable ids."""
    return [
        e.model_copy(update={"eventId": str(uuid.uuid5(uuid.NAMESPACE_URL, e.eventId))})
        for e in events
    ]


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def service(store=None, gateway=None, clock=None, meters=METERS) -> EngineService:
    return EngineService(lambda: list(meters), store=store, gateway=gateway, clock=clock or Clock())


def test_events_in_give_an_incident_with_a_verdict():
    s = service()
    s.rebuild()
    s.accept(power_outage_on("T5"))
    [incident] = s.incidents
    assert incident.assessment.result.cause is Cause.POWER
    assert incident.incident_id == "inc-0001"


def test_repeats_are_ignored_even_under_a_new_event_id():
    s = service()
    s.rebuild()
    events = power_outage_on("T5")
    s.accept(events)
    s.accept([e.model_copy(update={"eventId": "another-id"}) for e in events])
    assert len(s._events) == len(events)
    assert len(s.incidents) == 1


def test_out_of_order_events_give_the_same_verdict():
    events = power_outage_on("T5")
    ordered, shuffled = service(), service()
    ordered.rebuild()
    shuffled.rebuild()
    ordered.accept(events)
    for e in reversed(events):  # one at a time, newest first
        shuffled.accept([e])
    a, b = ordered.incidents[0].assessment, shuffled.incidents[0].assessment
    assert (a.result.cause, a.cluster.size) == (b.result.cause, b.cluster.size)


def test_an_unknown_sim_reloads_the_meter_list():
    loads = []
    extra = Meter("X-M01", "61499990001", "TX", "Carlton")

    def load():
        loads.append(1)
        return [*METERS, extra] if len(loads) > 1 else list(METERS)

    s = EngineService(load, clock=Clock(), topology_refresh=timedelta(0))
    s.rebuild()
    event = power_outage_on("T5")[0].model_copy(update={"msisdn": extra.msisdn, "eventId": "x"})
    s.accept([event])
    assert len(loads) == 2 and s._topology.get(extra.msisdn) is not None


def test_gateway_signals_feed_the_verdict():
    # Carlton meters with a postcode, so the engine can ask Network Availability about them.
    meters = [
        Meter(
            m.meter_id,
            m.msisdn,
            m.transformer_id,
            m.suburb,
            "3053" if m.suburb == "Carlton" else "3056",
        )
        for m in METERS
    ]
    fake = FakeGateway(outages={"Carlton": [{"suburb": "CARLTON", "start": "x", "end": None}]})
    gw = Gateway("http://gateway:8082", transport=httpx2.MockTransport(fake), auth=lambda _: {})
    s = service(gateway=gw, meters=meters)
    s.rebuild()
    s.accept(network_outage_in_carlton())
    assert s.incidents[0].assessment.result.cause is Cause.NETWORK
    assert any(r.url.path == "/v1/network-availability" for r in fake.requests)


URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def store():
    if not URL:
        pytest.skip("TEST_DATABASE_URL not set")
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS engine CASCADE")
        db.migrate(conn)
    conn = psycopg.connect(URL)
    yield EngineStore(conn)
    conn.close()


def count(store, sql):
    return store._conn.execute(sql).fetchone()[0]


def test_writes_incidents_and_a_verdict_with_a_summary(store):
    s = service(store=store)
    s.rebuild()
    s.accept(with_uuids(power_outage_on("T5")))
    s.tick()  # nothing changed, so no second verdict row
    row = store._conn.execute(
        "SELECT incident_id, cause, action, summary FROM engine.verdicts"
    ).fetchall()
    assert len(row) == 1
    incident_id, cause, action, summary = row[0]
    assert (incident_id, cause, action) == ("inc-0001", "POWER", "DISPATCH_POWER_CREW")
    assert summary.startswith("20 meters went silent. The most likely cause is a power outage")
    assert count(store, "SELECT count(*) FROM engine.events") == 20
    latest = store.latest_verdicts()
    assert latest[0]["incidentId"] == "inc-0001" and latest[0]["meterIds"][0] == "T5-M01"


def test_a_restart_rebuilds_from_the_database_and_keeps_the_incident_id(store):
    clock = Clock()
    first = service(store=store, clock=clock)
    first.rebuild()
    first.accept(with_uuids(power_outage_on("T5")))
    first.accept(with_uuids(network_outage_in_carlton()))
    ids_before = sorted(i.incident_id for i in first.incidents)

    clock.now = NOW + timedelta(seconds=30)
    second = service(store=store, clock=clock)  # a new instance, empty memory
    second.rebuild()
    assert sorted(i.incident_id for i in second.incidents) == ids_before
    # New incidents keep counting up instead of reusing inc-0001.
    assert second._tracker._next_number == 3


def test_an_aged_out_incident_is_closed_in_the_database(store):
    clock = Clock()
    s = service(store=store, clock=clock)
    s.rebuild()
    s.accept(with_uuids(power_outage_on("T5")))
    clock.now = NOW + timedelta(minutes=30)
    s.tick()
    assert count(store, "SELECT count(*) FROM engine.incidents WHERE closed_at IS NOT NULL") == 1
    assert store.latest_verdicts() == []

import json
from datetime import UTC, datetime

import httpx2

from engine.clustering import Cluster, SilentMeter
from engine.gateway import Gateway, inside, parse_multipolygon
from engine.topology import Meter

T0 = datetime(2026, 11, 25, 0, 5, tzinfo=UTC)
AREA = "MULTIPOLYGON(((144.95 -37.75,144.97 -37.75,144.97 -37.74,144.95 -37.74,144.95 -37.75)))"


def meter(n: int, suburb="Coburg", postcode="3058", lat=-37.745, lon=144.96) -> Meter:
    return Meter(f"M-{n:04d}", f"6141200{n:04d}", "T-01", suburb, postcode, "VIC", lat, lon)


def cluster(cid: str, *meters: Meter) -> Cluster:
    return Cluster(cid, tuple(SilentMeter(m, 7, T0) for m in meters))


def outage(area: str | None = AREA) -> dict:
    o = {"suburb": "COBURG", "start": "2026-11-25T00:00:00.000Z", "end": None}
    return {**o, "affected_area": area} if area else o


class FakeGateway:
    """Answers like telstra-gateway and records what was asked."""

    def __init__(self, outages=None, located=None, fail=False):
        self.outages = outages or {}  # suburb -> list of current outages
        self.located = located or {}  # msisdn -> TRUE / FALSE / PARTIAL / None
        self.fail = fail
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.fail:
            return httpx2.Response(502, json={"error": "TELSTRA_UNAVAILABLE"})
        if request.url.path == "/v1/network-availability":
            current = self.outages.get(request.url.params["suburb"], [])
            return httpx2.Response(200, json={"outages": {"current": current, "past": []}})
        body = json.loads(request.content)
        return httpx2.Response(
            200, json={"msisdn": body["msisdn"], "verificationResult": self.located[body["msisdn"]]}
        )


def gateway_for(fake: FakeGateway) -> Gateway:
    return Gateway("http://gateway:8082", transport=httpx2.MockTransport(fake), auth=lambda _: {})


def test_listed_outage_with_an_area_gives_suburbs_and_exact_sims():
    fake = FakeGateway(outages={"Coburg": [outage()]})
    big = cluster("c1", *(meter(n) for n in range(10)), meter(99, lat=-37.70))  # last one outside
    signals = gateway_for(fake).signals([big], {"c1": "inc-0001"})
    assert signals.outage_suburbs == {"Coburg"}
    assert signals.outage_msisdns == {meter(n).msisdn for n in range(10)}
    assert signals.moved_msisdns is None  # big clusters don't get location checks
    asked = fake.requests[0]
    assert asked.url.params["postcode"] == "3058" and asked.url.params["state"] == "VIC"
    assert asked.headers["x-incident-id"] == "inc-0001"


def test_one_question_per_suburb_however_many_meters():
    fake = FakeGateway()
    gateway_for(fake).signals([cluster("c1", *(meter(n) for n in range(20)))])
    assert len(fake.requests) == 1


def test_no_exact_sims_when_an_outage_has_no_area():
    fake = FakeGateway(outages={"Coburg": [outage(), outage(area=None)]})
    signals = gateway_for(fake).signals([cluster("c1", *(meter(n) for n in range(5)))])
    assert signals.outage_suburbs == {"Coburg"}
    assert signals.outage_msisdns is None


def test_small_cluster_gets_location_verification_and_false_means_moved():
    lone, pair_a, pair_b = meter(1), meter(2, "Brunswick", "3056"), meter(3, "Brunswick", "3056")
    fake = FakeGateway(located={lone.msisdn: "FALSE", pair_a.msisdn: "TRUE", pair_b.msisdn: None})
    signals = gateway_for(fake).signals([cluster("c1", lone), cluster("c2", pair_a, pair_b)])
    assert signals.moved_msisdns == {lone.msisdn}
    assert signals.outage_suburbs == set()  # asked, nothing listed


def test_gateway_down_means_signals_unknown_not_a_crash():
    signals = gateway_for(FakeGateway(fail=True)).signals([cluster("c1", meter(1))])
    assert signals.outage_suburbs is None
    assert signals.moved_msisdns is None
    assert signals.outage_msisdns is None


def test_point_in_multipolygon_with_a_hole():
    square_with_hole = "((0 0,10 0,10 10,0 10,0 0),(4 4,6 4,6 6,4 6,4 4))"
    wkt = f"MULTIPOLYGON({square_with_hole},((20 20,21 20,21 21,20 20)))"
    polygons = parse_multipolygon(wkt)
    assert len(polygons) == 2 and len(polygons[0]) == 2
    assert inside((1, 1), polygons)
    assert not inside((5, 5), polygons)  # in the hole
    assert inside((20.9, 20.5), polygons)
    assert not inside((15, 15), polygons)

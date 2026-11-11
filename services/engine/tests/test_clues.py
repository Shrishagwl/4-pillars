from datetime import UTC, datetime, timedelta

import pytest

from engine.clues import compute_clues
from engine.clustering import Cluster, SilentMeter
from engine.contracts import ReasonGroup
from engine.topology import Meter, Topology

T0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

# T1 (4 meters) and T2 (4 meters) are in Carlton; T3 (2 meters) is in Brunswick.
SIZES = {"T1": ("Carlton", 4), "T2": ("Carlton", 4), "T3": ("Brunswick", 2)}
METERS = {
    f"{t}-M{n}": Meter(f"{t}-M{n}", f"614{t[1]}{n:02d}", t, suburb)
    for t, (suburb, size) in SIZES.items()
    for n in range(1, size + 1)
}
TOPOLOGY = Topology(METERS.values())


def cluster(*drops: tuple[str, float, int]) -> Cluster:
    """Build a cluster from (meter_id, seconds after T0, reason code)."""
    members = sorted(
        (SilentMeter(METERS[mid], code, T0 + timedelta(seconds=secs)) for mid, secs, code in drops),
        key=lambda m: (m.silent_at, m.meter.meter_id),
    )
    return Cluster("c-test", tuple(members))


def test_topology_counts():
    assert TOPOLOGY.meters_on_transformer("T1") == 4
    assert TOPOLOGY.meters_in_suburb("Carlton") == 8
    assert TOPOLOGY.meters_on_transformer("nope") == 0


def test_power_outage_on_one_transformer():
    # All of T1: three last-gasp (code 6) within seconds, one found by timeout 4 minutes later.
    c = cluster(("T1-M1", 0, 6), ("T1-M2", 2, 6), ("T1-M3", 5, 6), ("T1-M4", 240, 7))
    clues = compute_clues(c, TOPOLOGY)

    assert clues.meter_count == 4
    assert clues.transformer_count == 1
    assert clues.crosses_transformers is False
    assert clues.transformer_share == 1.0
    assert clues.max_transformer_share == 1.0
    assert clues.suburb_share == 0.5  # 4 of Carlton's 8
    assert clues.spread_seconds == 240
    assert clues.burst_share == 0.75
    assert clues.reason_shares[ReasonGroup.DETACHED] == 0.75
    assert clues.reason_shares[ReasonGroup.DETECTION_TIMEOUT] == 0.25
    assert clues.outage_share is None  # not checked yet


def test_network_outage_across_two_transformers():
    # Part of T1 and part of T2, spread over two minutes, all timeouts.
    c = cluster(
        ("T1-M1", 0, 7), ("T1-M2", 40, 7), ("T1-M3", 80, 7), ("T2-M1", 60, 7), ("T2-M2", 120, 7)
    )
    clues = compute_clues(c, TOPOLOGY, outage_suburbs={"Carlton"})

    assert clues.crosses_transformers is True
    assert clues.transformer_count == 2
    assert clues.suburb_count == 1
    assert clues.transformer_share == pytest.approx(5 / 8)
    assert clues.max_transformer_share == 0.75  # T1: 3 of 4
    assert clues.suburb_share == pytest.approx(5 / 8)
    assert clues.spread_seconds == 120
    assert clues.burst_share == 0.4  # at most 2 of the 5 fall inside any 30 s
    assert clues.reason_shares[ReasonGroup.DETECTION_TIMEOUT] == 1.0
    assert clues.outage_share == 1.0


def test_single_meter():
    clues = compute_clues(cluster(("T2-M3", 0, 7)), TOPOLOGY, outage_suburbs=set())

    assert clues.meter_count == 1
    assert clues.transformer_share == 0.25
    assert clues.spread_seconds == 0
    assert clues.burst_share == 1.0
    assert clues.outage_share == 0.0  # checked, nothing listed


def test_outage_share_counts_only_meters_in_listed_suburbs():
    c = cluster(("T2-M1", 0, 7), ("T2-M2", 10, 7), ("T3-M1", 20, 7), ("T3-M2", 30, 7))
    clues = compute_clues(c, TOPOLOGY, outage_suburbs={"Brunswick"})

    assert clues.suburb_count == 2
    assert clues.outage_share == 0.5


def test_reason_shares_cover_every_group_and_sum_to_one():
    c = cluster(("T1-M1", 0, 6), ("T1-M2", 1, 7), ("T1-M3", 2, 4))
    shares = compute_clues(c, TOPOLOGY).reason_shares

    assert set(shares) == set(ReasonGroup)
    assert shares[ReasonGroup.UNKNOWN] == 0.0
    assert sum(shares.values()) == pytest.approx(1.0)


def test_burst_is_found_even_when_a_stray_meter_dropped_earlier():
    # T2-M1 dropped two minutes before T1 lost power. The burst is still 4 of 5.
    c = cluster(
        ("T2-M1", 0, 7), ("T1-M1", 120, 6), ("T1-M2", 121, 6), ("T1-M3", 123, 6), ("T1-M4", 125, 6)
    )
    clues = compute_clues(c, TOPOLOGY)

    assert clues.burst_share == 0.8
    assert clues.max_transformer_share == 1.0
    assert clues.transformer_share == pytest.approx(5 / 8)

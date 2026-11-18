from datetime import UTC, datetime, timedelta

import pytest

from engine.clustering import cluster_silent_meters
from engine.contracts import MeterSilentEvent, reason_group
from engine.topology import Meter, Topology

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

# Three transformers of four meters each. T1 and T2 are in Carlton, T3 is in Brunswick.
LAYOUT = {"T1": "Carlton", "T2": "Carlton", "T3": "Brunswick"}
METERS = [
    Meter(f"{t}-M{n}", f"61400{ti}{n:02d}", t, suburb)
    for ti, (t, suburb) in enumerate(LAYOUT.items(), start=1)
    for n in range(1, 5)
]
TOPOLOGY = Topology(METERS)
MSISDN = {m.meter_id: m.msisdn for m in METERS}


def silent(meter_id: str, minutes_ago: float, code: int = 7) -> MeterSilentEvent:
    when = NOW - timedelta(minutes=minutes_ago)
    return MeterSilentEvent(
        eventId=f"e-{meter_id}-{minutes_ago}",
        subscriptionId="sub-1",
        msisdn=MSISDN.get(meter_id, meter_id),
        reasonCode=code,
        reasonGroup=reason_group(code),
        eventTime=when,
        receivedAt=when,
    )


def ids(cluster) -> list[str]:
    return sorted(m.meter.meter_id for m in cluster.members)


def test_no_events_gives_no_clusters():
    assert cluster_silent_meters([], TOPOLOGY, NOW) == []


def test_single_meter_is_its_own_cluster():
    [cluster] = cluster_silent_meters([silent("T1-M1", 3)], TOPOLOGY, NOW)
    assert ids(cluster) == ["T1-M1"]
    assert cluster.size == 1
    assert cluster.transformer_ids == {"T1"}
    assert cluster.suburbs == {"Carlton"}


def test_meters_on_one_transformer_cluster_even_when_minutes_apart():
    # Last-gasp meters report at once, the rest only after the detection delay.
    events = [silent("T1-M1", 9, code=6), silent("T1-M2", 9, code=6), silent("T1-M3", 2)]
    [cluster] = cluster_silent_meters(events, TOPOLOGY, NOW)
    assert ids(cluster) == ["T1-M1", "T1-M2", "T1-M3"]
    assert cluster.first_silent_at == NOW - timedelta(minutes=9)
    assert cluster.last_silent_at == NOW - timedelta(minutes=2)


def test_suburb_wide_drop_joins_transformers_into_one_cluster():
    # T1 and T2 share Carlton and drop within a minute of each other.
    events = [silent("T1-M1", 5), silent("T1-M2", 4.5), silent("T2-M1", 4), silent("T2-M3", 3.5)]
    [cluster] = cluster_silent_meters(events, TOPOLOGY, NOW)
    assert cluster.transformer_ids == {"T1", "T2"}
    assert cluster.size == 4


def test_same_suburb_but_far_apart_in_time_stays_separate():
    events = [silent("T1-M1", 12), silent("T2-M1", 2)]
    clusters = cluster_silent_meters(events, TOPOLOGY, NOW)
    assert [ids(c) for c in clusters] == [["T1-M1"], ["T2-M1"]]


def test_different_suburbs_never_join():
    events = [silent("T1-M1", 3), silent("T3-M1", 3)]
    clusters = cluster_silent_meters(events, TOPOLOGY, NOW)
    assert sorted(ids(c) for c in clusters) == [["T1-M1"], ["T3-M1"]]


def test_events_outside_the_window_are_ignored():
    events = [silent("T1-M1", 16), silent("T1-M2", 15), silent("T1-M3", -1)]
    [cluster] = cluster_silent_meters(events, TOPOLOGY, NOW)
    assert ids(cluster) == ["T1-M2"]  # 16 min is too old, -1 min is in the future


def test_repeat_events_for_one_meter_keep_the_earliest():
    events = [silent("T1-M1", 2, code=7), silent("T1-M1", 8, code=6)]
    [cluster] = cluster_silent_meters(events, TOPOLOGY, NOW)
    assert cluster.size == 1
    assert cluster.members[0].reason_code == 6
    assert cluster.first_silent_at == NOW - timedelta(minutes=8)


def test_unknown_msisdn_is_skipped():
    events = [silent("61499999999", 3), silent("T1-M1", 3)]
    [cluster] = cluster_silent_meters(events, TOPOLOGY, NOW)
    assert ids(cluster) == ["T1-M1"]


def test_result_does_not_depend_on_event_order():
    events = [silent("T1-M1", 5), silent("T2-M1", 4), silent("T3-M2", 4), silent("T1-M4", 1)]
    forward = cluster_silent_meters(events, TOPOLOGY, NOW)
    backward = cluster_silent_meters(list(reversed(events)), TOPOLOGY, NOW)
    assert forward == backward
    assert [c.cluster_id for c in forward] == ["c-T1-M1", "c-T3-M2"]


def test_duplicate_msisdn_in_topology_is_rejected():
    with pytest.raises(ValueError, match="duplicate msisdn"):
        Topology([METERS[0], METERS[0]])

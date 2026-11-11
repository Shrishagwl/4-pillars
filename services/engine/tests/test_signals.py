"""The extra inputs: Location Verification, and the two proposed API changes."""

from datetime import timedelta

from test_pipeline import BY_ID, NOW, TOPOLOGY, silent

from engine.contracts import Action, Cause
from engine.evidence import build_evidence
from engine.pipeline import Signals, assess


def msisdn(meter_id: str) -> str:
    return BY_ID[meter_id].msisdn


def test_moved_sim_is_tamper():
    events = [silent("T1-M03", 100, 0)]
    signals = Signals(outage_suburbs=set(), moved_msisdns={msisdn("T1-M03")})

    [a] = assess(events, TOPOLOGY, NOW, signals=signals)

    assert a.clues.location_mismatch_share == 1.0
    assert a.result.cause is Cause.TAMPER
    assert a.decision.action is Action.INVESTIGATE_TAMPER
    assert "Location Verification: 100% of SIMs have moved" in build_evidence(
        a.cluster, a.clues, a.result, a.decision
    )


def test_sim_in_the_right_place_is_a_meter_fault():
    [a] = assess([silent("T1-M03", 100, 7)], TOPOLOGY, NOW, signals=Signals(moved_msisdns=set()))

    assert a.clues.location_mismatch_share == 0.0
    assert a.result.cause is Cause.METER_FAULT


def test_location_is_not_checked_for_big_clusters():
    events = [silent(f"T1-M{n:02d}", 100, 6) for n in range(1, 11)]
    moved = {msisdn(f"T1-M{n:02d}") for n in range(1, 11)}

    [a] = assess(events, TOPOLOGY, NOW, signals=Signals(moved_msisdns=moved))

    assert a.clues.location_mismatch_share is None
    assert a.result.cause is not Cause.TAMPER


def test_restored_meter_is_no_longer_silent():
    events = [silent("T1-M03", 300, 7), silent("T5-M01", 300, 7)]
    back = {msisdn("T1-M03"): NOW - timedelta(seconds=120)}

    without = assess(events, TOPOLOGY, NOW)
    with_restore = assess(events, TOPOLOGY, NOW, signals=Signals(restored=back))

    assert len(without) == 2
    assert [a.cluster.members[0].meter.meter_id for a in with_restore] == ["T5-M01"]


def test_restore_before_the_drop_or_in_the_future_does_not_count():
    events = [silent("T1-M03", 300, 7)]
    for back_at in (NOW - timedelta(seconds=400), NOW + timedelta(seconds=60)):
        signals = Signals(restored={msisdn("T1-M03"): back_at})
        assert len(assess(events, TOPOLOGY, NOW, signals=signals)) == 1


def test_outage_shape_beats_the_suburb_listing():
    # T1-M03 is in Carlton and Carlton has a listed outage, but the outage area does not
    # include this meter. Suburb-level says network; the exact shape says it is not.
    events = [silent("T1-M03", 100, 7)]

    [by_suburb] = assess(events, TOPOLOGY, NOW, outage_suburbs={"Carlton"})
    [by_shape] = assess(
        events,
        TOPOLOGY,
        NOW,
        signals=Signals(outage_suburbs={"Carlton"}, outage_msisdns={msisdn("T2-M01")}),
    )

    assert by_suburb.result.cause is Cause.NETWORK
    assert by_shape.clues.outage_share == 0.0
    assert by_shape.result.cause is Cause.METER_FAULT

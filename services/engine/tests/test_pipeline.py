"""Whole engine on small hand-made scenarios: events in, causes out."""

from datetime import UTC, datetime, timedelta

from engine.contracts import Action, Cause, MeterSilentEvent, reason_group
from engine.pipeline import assess
from engine.topology import Meter, Topology

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

# Six transformers of 20 meters. T1-T4 are in Carlton, T5-T6 in Brunswick.
SUBURB = {f"T{i}": "Carlton" if i <= 4 else "Brunswick" for i in range(1, 7)}
METERS = [
    Meter(f"{t}-M{n:02d}", f"614{t[1]}{n:04d}", t, suburb)
    for t, suburb in SUBURB.items()
    for n in range(1, 21)
]
TOPOLOGY = Topology(METERS)
BY_ID = {m.meter_id: m for m in METERS}


def silent(meter_id: str, seconds_ago: float, code: int) -> MeterSilentEvent:
    when = NOW - timedelta(seconds=seconds_ago)
    return MeterSilentEvent(
        eventId=f"e-{meter_id}",
        subscriptionId="sub-1",
        msisdn=BY_ID[meter_id].msisdn,
        reasonCode=code,
        reasonGroup=reason_group(code),
        eventTime=when,
        receivedAt=when,
    )


def power_outage_on(transformer: str) -> list[MeterSilentEvent]:
    # 14 meters send a last gasp (code 6) within 10 s; the other 6 time out 3 minutes later.
    last_gasp = [silent(f"{transformer}-M{n:02d}", 400 - n * 0.7, 6) for n in range(1, 15)]
    timed_out = [silent(f"{transformer}-M{n:02d}", 220 - n, 7) for n in range(15, 21)]
    return last_gasp + timed_out


def network_outage_in_carlton() -> list[MeterSilentEvent]:
    # 70% of every Carlton transformer drops, one meter every 5 s, all by timeout (code 7).
    hit = [f"T{t}-M{n:02d}" for t in range(1, 5) for n in range(1, 15)]
    return [silent(meter_id, 500 - i * 5, 7) for i, meter_id in enumerate(hit)]


def test_power_scenario_gives_power():
    [assessment] = assess(power_outage_on("T5"), TOPOLOGY, NOW)

    assert assessment.result.cause is Cause.POWER
    assert assessment.cluster.transformer_ids == {"T5"}
    assert assessment.clues.transformer_share == 1.0
    assert assessment.result.confidence == 0.9
    assert assessment.decision.action is Action.DISPATCH_POWER_CREW


def test_power_is_already_called_when_only_the_last_gasps_have_arrived():
    early = NOW - timedelta(seconds=380)  # 20 s into the outage
    [assessment] = assess(power_outage_on("T5"), TOPOLOGY, early)

    assert assessment.cluster.size == 14
    assert assessment.result.cause is Cause.POWER


def test_network_scenario_gets_more_confident_once_telstra_lists_it():
    events = network_outage_in_carlton()

    [before] = assess(events, TOPOLOGY, NOW, outage_suburbs=set())
    [after] = assess(events, TOPOLOGY, NOW, outage_suburbs={"Carlton"})

    assert before.result.cause is Cause.NETWORK
    assert after.result.cause is Cause.NETWORK
    assert before.cluster.size == 56
    assert before.result.confidence < 0.6 < after.result.confidence
    assert before.decision.action is Action.MANUAL_REVIEW
    assert after.decision.action is Action.WAIT_FOR_NETWORK


def test_a_lone_meter_fault_next_to_a_power_outage_stays_separate():
    events = power_outage_on("T5") + [silent("T1-M03", 100, 7)]

    by_cause = {a.result.cause: a for a in assess(events, TOPOLOGY, NOW)}

    assert set(by_cause) == {Cause.POWER, Cause.METER_FAULT}
    assert by_cause[Cause.METER_FAULT].cluster.size == 1
    assert by_cause[Cause.POWER].cluster.size == 20
    assert by_cause[Cause.METER_FAULT].decision.action is Action.DISPATCH_METER_TECH


def test_quiet_day_gives_nothing():
    assert assess([], TOPOLOGY, NOW) == []

from test_pipeline import NOW, TOPOLOGY, network_outage_in_carlton, power_outage_on, silent

from engine.contracts import Action, Cause
from engine.evidence import build_evidence, to_verdict
from engine.pipeline import assess


def evidence_for(events, **kwargs) -> list[str]:
    [a] = assess(events, TOPOLOGY, NOW, **kwargs)
    return build_evidence(a.cluster, a.clues, a.result, a.decision)


def test_power_evidence_covers_every_line_the_card_needs():
    lines = evidence_for(power_outage_on("T5"))

    starts = [line.split(":")[0] for line in lines]
    assert starts == [
        "Meters", "Where", "Timing", "Reason codes", "Outage API", "Verdict", "Action",
    ]  # fmt: skip
    assert lines[0] == "Meters: 20 silent (T5-M01, T5-M02, T5-M03 and 17 more)"
    assert "transformer(s) T5 in Brunswick; 100% of the meters" in lines[1]
    assert "70% dropped within 30 s of each other" in lines[2]
    assert lines[3] == "Reason codes: 70% detached (includes last gasp), 30% detection timeout"
    assert lines[4] == "Outage API: not checked yet"
    assert "POWER at 90%" in lines[5]
    assert lines[6].startswith("Action: DISPATCH_POWER_CREW")


def test_outage_line_has_three_states():
    events = network_outage_in_carlton()
    assert evidence_for(events)[4] == "Outage API: not checked yet"
    assert evidence_for(events, outage_suburbs=set())[4] == (
        "Outage API: no outage listed for these meters"
    )
    assert evidence_for(events, outage_suburbs={"Carlton"})[4] == (
        "Outage API: outage listed, covering 100% of the cluster"
    )


def test_single_meter_is_named_without_and_more():
    lines = evidence_for([silent("T1-M03", 100, 7)])
    assert lines[0] == "Meters: 1 silent (T1-M03)"


def test_to_verdict_matches_the_shared_contract():
    [a] = assess(power_outage_on("T5"), TOPOLOGY, NOW)
    verdict = to_verdict("inc-0001", a.cluster, a.clues, a.result, a.decision, NOW)

    assert verdict.incidentId == "inc-0001"
    assert verdict.meterCount == 20
    assert verdict.cause is Cause.POWER
    assert verdict.action is Action.DISPATCH_POWER_CREW
    assert len(verdict.evidence) == 7
    assert verdict.model_dump(mode="json")["updatedAt"].startswith("2026-11-12T10:00:00")

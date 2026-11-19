from datetime import timedelta

from test_pipeline import NOW, TOPOLOGY, network_outage_in_carlton, power_outage_on, silent

from engine.contracts import Action, Cause
from engine.pipeline import Signals
from engine.tracker import IncidentTracker


def until(events, when):
    return [e for e in events if e.eventTime <= when]


def test_network_confidence_rises_when_the_outage_is_listed():
    events = network_outage_in_carlton()
    tracker = IncidentTracker(TOPOLOGY)

    # Two minutes in: a few meters, nothing listed.
    early = NOW - timedelta(seconds=380)
    [incident] = tracker.update(until(events, early), early, Signals(outage_suburbs=set()))
    first_id = incident.incident_id
    assert incident.assessment.decision.action is Action.MANUAL_REVIEW

    # All meters have dropped, still nothing listed.
    middle = NOW - timedelta(seconds=120)
    [incident] = tracker.update(until(events, middle), middle, Signals(outage_suburbs=set()))
    assert incident.incident_id == first_id

    # Telstra lists the outage.
    [incident] = tracker.update(events, NOW, Signals(outage_suburbs={"Carlton"}))
    assert incident.incident_id == first_id
    assert incident.assessment.decision.action is Action.WAIT_FOR_NETWORK

    confidences = [change.confidence for change in incident.history]
    assert confidences == [0.55, 0.85]
    last = incident.history[-1]
    assert last.cause is Cause.NETWORK
    assert "Outage API not listed -> listed" in last.why
    assert "rule 'network-unlisted' -> 'network-listed'" in last.why
    assert incident.history[0].why == "incident opened"


def test_no_history_line_when_nothing_about_the_verdict_changes():
    events = power_outage_on("T5")
    tracker = IncidentTracker(TOPOLOGY)

    tracker.update(events, NOW - timedelta(seconds=30))
    [incident] = tracker.update(events, NOW)

    assert len(incident.history) == 1


def test_separate_incidents_get_separate_ids_and_keep_them():
    events = power_outage_on("T5") + [silent("T1-M03", 100, 7)]
    tracker = IncidentTracker(TOPOLOGY)

    first = {i.assessment.result.cause: i.incident_id for i in tracker.update(events, NOW)}
    later = NOW + timedelta(seconds=30)
    second = {i.assessment.result.cause: i.incident_id for i in tracker.update(events, later)}

    assert first == second
    assert sorted(first.values()) == ["inc-0001", "inc-0002"]


def test_incident_closes_when_it_ages_out_of_the_window():
    tracker = IncidentTracker(TOPOLOGY)
    tracker.update([silent("T1-M03", 100, 7)], NOW)

    much_later = NOW + timedelta(minutes=20)
    assert tracker.update([silent("T1-M03", 100, 7)], much_later) == []
    [closed] = tracker.closed
    assert closed.closed_at == much_later
    assert closed.assessment.result.cause is Cause.METER_FAULT  # last verdict is kept


def test_incident_gives_a_verdict_for_the_dashboard():
    tracker = IncidentTracker(TOPOLOGY)
    [incident] = tracker.update(power_outage_on("T5"), NOW)

    verdict = incident.verdict(NOW)
    assert verdict.incidentId == "inc-0001"
    assert verdict.cause is Cause.POWER
    assert verdict.evidence

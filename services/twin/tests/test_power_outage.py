from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest

from twin.clock import DEFAULT_START, HEARTBEAT_EVERY_MIN
from twin.faults import LOC_DETECTION_TIMEOUT, LOC_LAST_GASP
from twin.grid import build_twin
from twin.run import run_scenario
from twin.scenario import Cause, load_scenario, parse_scenario

SCENARIOS = Path(__file__).parent.parent / "scenarios"


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(SCENARIOS / "power-outage.yaml")


@pytest.fixture(scope="module")
def result(scenario):
    return run_scenario(scenario, seed=1)


def test_answer_key_says_power_on_one_transformer(result):
    [incident] = result.answer_key
    assert incident.cause is Cause.POWER
    assert incident.target.startswith("T-")
    assert (
        timedelta(minutes=60)
        <= incident.restored_at - incident.started_at
        <= timedelta(minutes=120)
    )


def test_every_meter_on_the_transformer_reports_and_no_other_meter_does(result):
    [incident] = result.answer_key
    by_msisdn = {r.msisdn for r in result.loc_reports}
    assert len(by_msisdn) == len(result.loc_reports)  # one report per meter
    twin = build_twin(result.twin_seed)
    on_transformer = {m.msisdn for m in twin.meters_on(incident.target)}
    assert by_msisdn == on_transformer


def test_most_send_a_last_gasp_within_seconds_the_rest_time_out_later(result):
    [incident] = result.answer_key
    codes = Counter(r.reason_code for r in result.loc_reports)
    assert set(codes) == {LOC_LAST_GASP, LOC_DETECTION_TIMEOUT}
    assert 0.5 < codes[LOC_LAST_GASP] / len(result.loc_reports) < 0.9

    for r in result.loc_reports:
        after = (r.event_time - incident.started_at).total_seconds()
        if r.reason_code == LOC_LAST_GASP:
            assert 0 <= after <= 10
        else:
            assert 120 <= after <= 250


def test_cut_meters_stop_heartbeating_and_come_back_after_the_repair(result):
    [incident] = result.answer_key
    cut = set(incident.meter_ids)
    during = {
        b.meter_id
        for b in result.heartbeats
        if incident.started_at < b.time <= incident.restored_at
    }
    after = {
        b.meter_id
        for b in result.heartbeats
        if incident.restored_at < b.time <= incident.restored_at + timedelta(minutes=15)
    }
    assert during.isdisjoint(cut)
    assert cut <= after


def test_same_seed_same_run_different_seed_different_run(scenario):
    a, b, c = (run_scenario(scenario, seed=s) for s in (5, 5, 6))
    assert a == b
    assert a.loc_reports != c.loc_reports


def test_a_meter_already_offline_sends_no_second_report():
    # Two power faults on the same transformer: the second finds every meter already dark.
    s = parse_scenario(
        {
            "name": "double-cut",
            "duration_min": 30,
            "faults": [
                {"kind": "power", "at_min": 5, "transformer": "T-02"},
                {"kind": "power", "at_min": 10, "transformer": "T-02"},
            ],
        }
    )
    result = run_scenario(s, seed=0)
    first, second = result.answer_key
    assert len(result.loc_reports) == len(first.meter_ids)


def test_reports_convert_to_telstras_json_shape(result):
    report = result.loc_reports[0].to_telstra()
    assert report["monitoringType"] == "LOSS_OF_CONNECTIVITY"
    assert report["eventTime"].endswith("Z")
    assert set(report) == {"monitoringType", "msisdn", "lossOfConnectReason", "eventTime"}


def test_before_the_fault_every_meter_beats_once_per_cycle(result):
    # The clock steps before it reports, so the first cycle is minutes 1 to 15 (not 0 to 14).
    start = DEFAULT_START
    first_cycle = {
        b.meter_id
        for b in result.heartbeats
        if start < b.time <= start + timedelta(minutes=HEARTBEAT_EVERY_MIN)
    }
    assert len(first_cycle) == len(build_twin(result.twin_seed).meters)

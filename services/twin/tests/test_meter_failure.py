from datetime import timedelta
from pathlib import Path

import pytest

from twin.faults import TIMEOUT_CODES
from twin.grid import build_twin
from twin.run import run_scenario
from twin.scenario import Cause, ScenarioError, load_scenario, parse_scenario

SCENARIOS = Path(__file__).parent.parent / "scenarios"


# --- one meter breaks on its own ---------------------------------------------------------------


@pytest.fixture(scope="module")
def failure():
    return run_scenario(load_scenario(SCENARIOS / "meter-failure.yaml"), seed=1)


def test_answer_key_says_meter_fault_on_one_meter(failure):
    [incident] = failure.answer_key
    assert incident.cause is Cause.METER_FAULT
    assert incident.meter_ids == (incident.target,)
    assert timedelta(minutes=60) <= incident.restored_at - incident.started_at
    assert incident.restored_at - incident.started_at <= timedelta(minutes=120)


def test_exactly_one_code_7_and_no_last_gasp(failure):
    [incident] = failure.answer_key
    [report] = failure.loc_reports
    msisdn = {m.meter_id: m.msisdn for m in build_twin(failure.twin_seed).meters}
    assert report.msisdn == msisdn[incident.target]
    assert report.reason_code in TIMEOUT_CODES
    delay = report.event_time - incident.started_at
    assert timedelta(minutes=2) <= delay <= timedelta(minutes=5)


def test_the_broken_meter_is_silent_until_replaced_then_beats_again(failure):
    [incident] = failure.answer_key
    meter = incident.target
    beats = [b.time for b in failure.heartbeats if b.meter_id == meter]
    gap = timedelta(minutes=1)
    assert not [t for t in beats if incident.started_at + gap < t <= incident.restored_at]
    assert [t for t in beats if t > incident.restored_at]


def test_meter_failure_runs_vary_by_seed():
    s = load_scenario(SCENARIOS / "meter-failure.yaml")
    targets = {run_scenario(s, seed).answer_key[0].target for seed in range(5)}
    assert len(targets) > 1


# --- background dropouts on a normal day ---------------------------------------------------------


@pytest.fixture(scope="module")
def normal_day():
    return run_scenario(load_scenario(SCENARIOS / "normal-day.yaml"), seed=1)


def test_a_normal_day_has_no_incidents_but_some_dropouts(normal_day):
    assert normal_day.answer_key == ()
    # 4 an hour for 6 hours: about 24, and certainly more than a handful.
    assert 10 <= len(normal_day.background) <= 45


def test_only_dropouts_that_outlast_the_timer_are_reported(normal_day):
    reported = {d.msisdn for d in normal_day.background if d.reported}
    assert {r.msisdn for r in normal_day.loc_reports} == reported
    assert all(r.reason_code in TIMEOUT_CODES for r in normal_day.loc_reports)
    # Some are short enough to slip under Telstra's timer, some are not.
    assert any(d.reported for d in normal_day.background)
    assert not all(d.reported for d in normal_day.background)


def test_dropped_meters_come_back_by_themselves(normal_day):
    for d in normal_day.background:
        if d.back_at is None:
            continue
        later = [
            b for b in normal_day.heartbeats if b.meter_id == d.meter_id and b.time > d.back_at
        ]
        quiet = [
            b
            for b in normal_day.heartbeats
            if b.meter_id == d.meter_id
            and d.dropped_at + timedelta(minutes=1) < b.time <= d.back_at - timedelta(minutes=1)
        ]
        assert not quiet
        if d.back_at + timedelta(minutes=15) < max(b.time for b in normal_day.heartbeats):
            assert later


def test_noise_does_not_change_where_or_when_a_fault_happens():
    # Noise has its own random generator, so adding it leaves the fault exactly as it was.
    fault = {"kind": "power", "at_min": [20, 40], "transformer": "random"}
    quiet = parse_scenario({"name": "x", "duration_min": 120, "faults": [fault]})
    noisy = parse_scenario(
        {"name": "x", "duration_min": 120, "faults": [fault], "noise": {"dropouts_per_hour": 10}}
    )
    a = run_scenario(quiet, seed=3).answer_key[0]
    b = run_scenario(noisy, seed=3).answer_key[0]
    assert (a.target, a.started_at, a.meter_ids) == (b.target, b.started_at, b.meter_ids)


def test_same_seed_same_normal_day():
    s = load_scenario(SCENARIOS / "normal-day.yaml")
    assert run_scenario(s, 2) == run_scenario(s, 2)


@pytest.mark.parametrize(
    ("noise", "message"),
    [
        ({"dropouts_per_hour": -1}, "dropouts_per_hour"),
        ({"back_after_min": [0, 5]}, "at least 1 minute"),
        ({"dropout_per_hour": 2}, "dropout_per_hour"),  # typo
    ],
)
def test_bad_noise_settings_are_rejected(noise, message):
    with pytest.raises(ScenarioError, match=message):
        parse_scenario({"name": "x", "duration_min": 60, "noise": noise})

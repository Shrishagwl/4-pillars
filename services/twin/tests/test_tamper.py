from datetime import timedelta
from pathlib import Path

import pytest

from twin.faults import LOC_DETECTION_TIMEOUT, LOC_LAST_GASP
from twin.grid import build_twin, distance_m
from twin.run import run_scenario
from twin.scenario import Cause, ScenarioError, load_scenario, parse_scenario

SCENARIOS = Path(__file__).parent.parent / "scenarios"


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(SCENARIOS / "tamper.yaml")


@pytest.fixture(scope="module")
def result(scenario):
    return run_scenario(scenario, seed=1)


@pytest.fixture(scope="module")
def home(result):
    [incident] = result.answer_key
    return next(m for m in build_twin(result.twin_seed).meters if m.meter_id == incident.target)


def test_answer_key_says_tamper_on_one_meter_never_repaired(result):
    [incident] = result.answer_key
    assert incident.cause is Cause.TAMPER
    assert incident.meter_ids == (incident.target,)
    assert incident.restored_at is None


def test_it_goes_silent_with_one_report(result, home):
    [report] = result.loc_reports
    assert report.msisdn == home.msisdn
    assert report.reason_code in {LOC_LAST_GASP, LOC_DETECTION_TIMEOUT}


def test_its_sim_turns_up_kilometres_from_home(result, home):
    [incident] = result.answer_key
    [moved] = result.relocations
    assert moved.msisdn == home.msisdn
    gap = moved.moved_at - incident.started_at
    assert timedelta(minutes=5) <= gap <= timedelta(minutes=30)
    away = distance_m(home.lat, home.lon, moved.lat, moved.lon)
    assert 2_000 <= away <= 10_000
    # Telstra's sandbox checks circles of at least 1 km, so this is always a clear FALSE.
    assert abs(away - moved.distance_m) < 1


def test_heartbeats_stop_then_resume_from_the_new_place(result, home):
    [incident] = result.answer_key
    [moved] = result.relocations
    beats = [b.time for b in result.heartbeats if b.meter_id == home.meter_id]
    gap = timedelta(minutes=1)
    assert not [t for t in beats if incident.started_at + gap < t <= moved.moved_at]
    assert [t for t in beats if t > moved.moved_at]


def test_moved_msisdns_only_after_it_has_moved(result, home):
    [moved] = result.relocations
    assert result.moved_msisdns(moved.moved_at - timedelta(seconds=1)) == set()
    assert result.moved_msisdns(moved.moved_at) == {home.msisdn}


def test_both_report_codes_happen_across_seeds(scenario):
    codes = {run_scenario(scenario, seed).loc_reports[0].reason_code for seed in range(12)}
    assert codes == {LOC_LAST_GASP, LOC_DETECTION_TIMEOUT}


def test_same_seed_same_run_different_seeds_differ(scenario):
    assert run_scenario(scenario, 4) == run_scenario(scenario, 4)
    places = {run_scenario(scenario, seed).relocations[0].lat for seed in range(4)}
    assert len(places) == 4


def test_a_sim_that_reappears_after_the_run_ends_has_no_relocation():
    s = parse_scenario(
        {
            "name": "late",
            "duration_min": 30,
            "faults": [
                {"kind": "tamper", "at_min": 20, "meter": "M-0001", "reappear_after_min": [15, 20]}
            ],
        }
    )
    result = run_scenario(s, seed=0)
    assert result.relocations == ()
    assert result.answer_key[0].cause is Cause.TAMPER


def test_a_tampered_meter_cannot_be_repaired_in_place():
    with pytest.raises(ScenarioError, match="reappear_after_min"):
        parse_scenario(
            {
                "name": "x",
                "duration_min": 60,
                "faults": [
                    {"kind": "tamper", "at_min": 5, "meter": "random", "restore_after_min": 10}
                ],
            }
        )

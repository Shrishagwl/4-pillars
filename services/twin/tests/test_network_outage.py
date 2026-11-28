from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest

from twin.faults import TIMEOUT_CODES
from twin.grid import build_twin
from twin.run import run_scenario
from twin.scenario import Cause, ScenarioError, load_scenario, parse_scenario

SCENARIOS = Path(__file__).parent.parent / "scenarios"


@pytest.fixture(scope="module")
def scenario():
    return load_scenario(SCENARIOS / "network-outage.yaml")


@pytest.fixture(scope="module")
def result(scenario):
    return run_scenario(scenario, seed=1)


@pytest.fixture(scope="module")
def twin(result):
    return build_twin(result.twin_seed)


def test_answer_key_says_network_in_one_suburb(result, twin):
    [incident] = result.answer_key
    assert incident.cause is Cause.NETWORK
    assert incident.target in {s.name for s in twin.suburbs}


def test_most_but_not_all_of_the_suburb_goes_quiet(result, twin):
    [incident] = result.answer_key
    suburb_meters = {m.meter_id for m in twin.meters_in(incident.target)}
    hit = set(incident.meter_ids)
    assert hit < suburb_meters  # strictly fewer: some meters keep their signal
    assert 0.6 <= len(hit) / len(suburb_meters) <= 0.9


def test_reports_come_only_from_the_hit_meters_all_code_7(result, twin):
    [incident] = result.answer_key
    msisdn_of = {m.meter_id: m.msisdn for m in twin.meters}
    assert {r.msisdn for r in result.loc_reports} == {msisdn_of[m] for m in incident.meter_ids}
    assert {r.reason_code for r in result.loc_reports} <= TIMEOUT_CODES


def test_it_cuts_across_transformers_unlike_a_power_cut(result, twin):
    # The fingerprint that separates it from a power outage: many transformers each lose part
    # of their meters, instead of one transformer losing all of them.
    [incident] = result.answer_key
    transformer_of = {m.meter_id: m.transformer_id for m in twin.meters}
    per_transformer = Counter(transformer_of[m] for m in incident.meter_ids)
    assert len(per_transformer) >= 3
    partly_hit = [t for t, n in per_transformer.items() if n < len(twin.meters_on(t))]
    assert partly_hit


def test_drops_spread_over_minutes_not_seconds(result):
    [incident] = result.answer_key
    times = sorted(r.event_time for r in result.loc_reports)
    assert times[0] >= incident.started_at + timedelta(seconds=120)  # detection delay
    assert times[-1] - times[0] > timedelta(minutes=2)
    assert times[-1] <= incident.started_at + timedelta(seconds=180 + 240)


def test_telstra_lists_the_outage_after_a_lag(result, twin):
    [incident] = result.answer_key
    [notice] = result.outages
    assert notice.suburb == incident.target
    assert notice.postcode == {s.name: s.postcode for s in twin.suburbs}[incident.target]
    assert notice.started_at == incident.started_at
    lag = notice.listed_at - notice.started_at
    assert timedelta(minutes=10) <= lag <= timedelta(minutes=30)
    assert notice.restored_at == incident.restored_at


def test_hit_meters_stop_heartbeating_then_recover(result):
    [incident] = result.answer_key
    hit = set(incident.meter_ids)
    quiet_from = incident.started_at + timedelta(minutes=1)
    during = {b.meter_id for b in result.heartbeats if quiet_from < b.time <= incident.restored_at}
    after = {
        b.meter_id
        for b in result.heartbeats
        if incident.restored_at < b.time <= incident.restored_at + timedelta(minutes=15)
    }
    assert during.isdisjoint(hit)
    assert hit <= after


def test_same_seed_same_run(scenario):
    assert run_scenario(scenario, seed=3) == run_scenario(scenario, seed=3)
    assert run_scenario(scenario, seed=3).loc_reports != run_scenario(scenario, seed=4).loc_reports


def test_a_notice_due_after_the_run_ends_is_not_listed():
    s = parse_scenario(
        {
            "name": "late-notice",
            "duration_min": 20,
            "faults": [{"kind": "network", "at_min": 15, "suburb": "Coburg"}],
        }
    )
    result = run_scenario(s, seed=0)
    assert result.outages == ()
    assert result.answer_key[0].cause is Cause.NETWORK


def test_a_meter_already_down_from_a_power_cut_is_not_counted_twice():
    # Power cut on a Coburg-side transformer first, then the Coburg network fails.
    twin = build_twin(42)
    in_coburg = {m.transformer_id for m in twin.meters_in("Coburg")}
    transformer = sorted(in_coburg)[0]
    s = parse_scenario(
        {
            "name": "power-then-network",
            "duration_min": 60,
            "faults": [
                {"kind": "power", "at_min": 5, "transformer": transformer},
                {"kind": "network", "at_min": 10, "suburb": "Coburg"},
            ],
        }
    )
    power, network = run_scenario(s, seed=0).answer_key
    assert set(power.meter_ids).isdisjoint(network.meter_ids)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"drop_share": [0.9, 0.6]}, "low <= high"),
        ({"drop_share": [0.5, 1.5]}, "above 1"),
        ({"notice_lag_min": [-5, 10]}, "low <= high"),
    ],
)
def test_bad_ranges_are_rejected(override, message):
    fault = {"kind": "network", "at_min": 5, "suburb": "Coburg"} | override
    with pytest.raises(ScenarioError, match=message):
        parse_scenario({"name": "bad", "duration_min": 30, "faults": [fault]})

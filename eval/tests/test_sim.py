from datetime import timedelta

import pytest
from engine.contracts import Cause, ReasonGroup

from evaluation.sim import KINDS, SimSettings, build_grid, scenario_for, simulate

QUIET = SimSettings(blips_per_hour=0, stale_outage_rate=0)


def test_same_seed_gives_the_same_run():
    a, b = simulate("power", 7), simulate("power", 7)
    assert a.events == b.events
    assert a.truth_meter_ids == b.truth_meter_ids
    assert simulate("power", 8).events != a.events


def test_grid_is_the_twins_map():
    grid = build_grid(42)
    assert len(grid.topology) == len(grid.meters) > 1000
    assert len(grid.by_transformer) == 20
    assert set(grid.transformer_suburb) == set(grid.by_transformer)


def test_settings_reach_the_twin_scenario():
    settings = SimSettings(last_gasp_rate=0.2, detection_delay_s=60, outage_api_lag_s=600)
    power = scenario_for("power", settings).faults[0]
    network = scenario_for("network", settings).faults[0]
    assert power.last_gasp_share == 0.2
    assert power.detection_delay_s == (40, 80)
    assert network.notice_lag_min == (5, 15)
    assert scenario_for("power", QUIET).noise is None


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_has_an_answer_key_and_sorted_events(kind):
    run = simulate(kind, 1)
    assert run.truth_meter_ids
    assert list(run.event_times) == sorted(run.event_times)
    assert run.start < run.fault_at < run.end
    fault_msisdns = {m.msisdn for m in run.grid.meters if m.meter_id in run.truth_meter_ids}
    assert fault_msisdns <= {e.msisdn for e in run.events}


def test_power_cut_hits_one_transformer_with_last_gasps():
    run = simulate("power", 3, QUIET)
    by_id = {m.meter_id: m for m in run.grid.meters}
    assert run.truth is Cause.POWER
    assert len({by_id[mid].transformer_id for mid in run.truth_meter_ids}) == 1
    gasps = sum(1 for e in run.events if e.reasonGroup is ReasonGroup.DETACHED)  # codes 0 or 6
    assert 0.5 < gasps / len(run.events) < 0.9  # about 70%


def test_network_outage_is_listed_late_and_crosses_transformers():
    run = simulate("network", 2, SimSettings(blips_per_hour=0, outage_api_lag_s=300))
    by_id = {m.meter_id: m for m in run.grid.meters}
    [listing] = run.listings
    assert run.truth is Cause.NETWORK
    assert len({by_id[mid].transformer_id for mid in run.truth_meter_ids}) >= 2
    assert run.outage_suburbs_at(run.fault_at) == set()
    assert run.outage_suburbs_at(run.end) == {listing.suburb}
    assert len(run.outage_msisdns_at(run.end)) == len(run.truth_meter_ids)


def test_tamper_moves_the_sim_later_and_meter_fault_does_not():
    tamper = simulate("tamper", 1, SimSettings(tamper_detect_rate=1.0))
    fault = simulate("meter_fault", 1)
    assert len(tamper.truth_meter_ids) == len(fault.truth_meter_ids) == 1
    [moved_at] = tamper.moves.values()
    assert tamper.moved_msisdns_at(tamper.fault_at) == set()
    assert len(tamper.moved_msisdns_at(moved_at)) == 1
    assert fault.moves == {}


def test_dropouts_come_back_and_are_not_the_fault():
    run = simulate("meter_fault", 4, SimSettings(blips_per_hour=60))
    assert len(run.restores) > 5
    fault_msisdns = {m.msisdn for m in run.grid.meters if m.meter_id in run.truth_meter_ids}
    assert not fault_msisdns & set(run.restores)
    assert len(simulate("meter_fault", 4, QUIET).events) == 1


def test_events_until_only_returns_what_has_happened():
    run = simulate("network", 5)
    halfway = run.fault_at + timedelta(seconds=300)
    seen = run.events_until(halfway)
    assert 0 < len(seen) < len(run.events)
    assert all(e.eventTime <= halfway for e in seen)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="unknown kind"):
        simulate("flood", 1)

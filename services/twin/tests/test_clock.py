from collections import Counter
from datetime import timedelta

import pytest

from twin.clock import DEFAULT_START, HEARTBEAT_EVERY_MIN, TwinClock
from twin.grid import build_twin


@pytest.fixture(scope="module")
def twin():
    return build_twin(42)


def test_clock_moves_one_minute_per_step(twin):
    clock = TwinClock(twin)
    clock.step()
    clock.step()
    assert clock.minute == 2
    assert clock.now == DEFAULT_START + timedelta(minutes=2)


def test_quiet_hour_every_meter_beats_exactly_four_times(twin):
    clock = TwinClock(twin)
    beats = Counter(b.meter_id for b in clock.run(60))
    assert len(beats) == len(twin.meters)
    assert set(beats.values()) == {60 // HEARTBEAT_EVERY_MIN}


def test_quiet_run_is_steady_minute_to_minute(twin):
    # Heartbeats are spread across the cycle, not bunched on one minute, and every 15-minute
    # cycle repeats the same pattern while nothing is wrong.
    clock = TwinClock(twin)
    per_minute = [len(clock.step()) for _ in range(3 * HEARTBEAT_EVERY_MIN)]
    average = len(twin.meters) / HEARTBEAT_EVERY_MIN
    assert all(0.6 * average <= n <= 1.4 * average for n in per_minute)
    cycles = [per_minute[i : i + HEARTBEAT_EVERY_MIN] for i in (0, 15, 30)]
    assert cycles[0] == cycles[1] == cycles[2]


def test_state_can_be_queried_at_any_time(twin):
    clock = TwinClock(twin)
    meter_id = twin.meters[0].meter_id
    assert clock.state(meter_id).online
    assert clock.state(meter_id).last_heartbeat is None
    for _ in range(20):
        clock.step()
    state = clock.state(meter_id)
    assert state.online
    assert clock.now - state.last_heartbeat < timedelta(minutes=HEARTBEAT_EVERY_MIN)
    assert clock.online_count() == len(twin.meters)


def test_state_is_a_copy(twin):
    clock = TwinClock(twin)
    meter_id = twin.meters[0].meter_id
    clock.state(meter_id).powered = False
    assert clock.state(meter_id).powered


def test_unpowered_meters_go_quiet_and_resume_when_power_returns(twin):
    clock = TwinClock(twin)
    feeder = twin.transformers[0].id
    cut = {m.meter_id for m in twin.meters_on(feeder)}

    clock.set_powered(cut, False)
    assert clock.online_count() == len(twin.meters) - len(cut)
    during = {b.meter_id for b in clock.run(30)}
    assert during.isdisjoint(cut)

    clock.set_powered(cut, True)
    after = {b.meter_id for b in clock.run(15)}
    assert cut <= after


@pytest.mark.parametrize("switch", ["set_connected", "set_healthy"])
def test_any_switch_off_takes_a_meter_offline(twin, switch):
    clock = TwinClock(twin)
    meter_id = twin.meters[0].meter_id
    getattr(clock, switch)([meter_id], False)
    assert not clock.state(meter_id).online
    assert meter_id not in {b.meter_id for b in clock.run(15)}


def test_same_seed_gives_the_same_heartbeat_schedule():
    a = list(TwinClock(build_twin(42)).run(15))
    b = list(TwinClock(build_twin(42)).run(15))
    assert a == b

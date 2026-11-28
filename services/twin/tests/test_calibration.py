"""The twin's settings match docs/twin-calibration.md. If one of these fails, either the twin
drifted from the documented value or the doc needs updating with a new source."""

from collections import Counter
from pathlib import Path

from twin.clock import HEARTBEAT_EVERY_MIN
from twin.faults import FIVE_G_SHARE, LAST_GASP_CODES, TIMEOUT_CODES, on_5g
from twin.grid import METERS_PER_TRANSFORMER, build_twin
from twin.run import run_scenario
from twin.scenario import load_scenario

SCENARIOS = Path(__file__).parents[1] / "scenarios"


def test_no_3g_codes_because_telstra_3g_is_closed():
    sgsn = {1, 3, 5}  # UE_DETACHED_SGSN, MAX_DETECTION_TIME_EXPIRED_SGSN, UE_PURGED_SGSN
    seen = Counter()
    for name in ("power-outage", "network-outage", "meter-failure", "tamper", "normal-day"):
        scenario = load_scenario(SCENARIOS / f"{name}.yaml")
        for seed in range(3):
            seen.update(r.reason_code for r in run_scenario(scenario, seed).loc_reports)
    assert not set(seen) & sgsn
    assert set(seen) <= LAST_GASP_CODES | TIMEOUT_CODES
    # Mostly 4G (MME) codes, a few 5G (AMF) ones.
    four_g = seen[0] + seen[2]
    assert four_g / sum(seen.values()) > 0.75


def test_about_one_sim_in_ten_is_on_5g():
    twin = build_twin(42)
    share = sum(on_5g(m.msisdn) for m in twin.meters) / len(twin.meters)
    assert abs(share - FIVE_G_SHARE) < 0.03


def test_meters_per_transformer_in_the_documented_range():
    low, high = METERS_PER_TRANSFORMER
    assert (low, high) == (50, 150)
    for twin_seed in (42, 7, 2026):
        counts = Counter(m.transformer_id for m in build_twin(twin_seed).meters)
        assert all(low <= n <= high for n in counts.values())


def test_power_outages_last_one_to_three_hours():
    scenario = load_scenario(SCENARIOS / "power-outage.yaml")
    hours = []
    for seed in range(10):
        [incident] = run_scenario(scenario, seed).answer_key
        hours.append((incident.restored_at - incident.started_at).total_seconds() / 3600)
    assert all(1 <= h <= 3 for h in hours)
    assert max(hours) > 2  # the wider range is actually used


def test_last_gasp_share_is_the_documented_estimate():
    scenario = load_scenario(SCENARIOS / "power-outage.yaml")
    reports = [r for seed in range(10) for r in run_scenario(scenario, seed).loc_reports]
    share = sum(r.reason_code in LAST_GASP_CODES for r in reports) / len(reports)
    assert 0.6 < share < 0.8  # 0.7 in the scenario, an estimate (no public figure)


def test_heartbeat_is_faster_than_the_meters_30_minute_interval():
    # Meters record every 30 min (Energy Victoria); the twin's "still alive" tick is 15 min.
    assert HEARTBEAT_EVERY_MIN == 15

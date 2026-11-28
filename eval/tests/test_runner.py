import csv
import json

from engine.contracts import Action, Cause
from engine.decision import DEFAULT_COSTS

from evaluation.metrics import brier, f1_per_cause, results_table, summarise
from evaluation.runner import run_batch, write_results
from evaluation.sim import SimSettings, simulate
from evaluation.systems import B0, B1, Baseline, EngineSystem, Outcome, jaccard

# No background dropouts, no stale listing, and Telstra lists a network outage within ~5 min.
QUIET = SimSettings(blips_per_hour=0, stale_outage_rate=0, outage_api_lag_s=300)
ENGINE = EngineSystem()


def outcome(truth: Cause, predicted: Cause | None, **overrides) -> Outcome:
    base = {
        "system": "test",
        "kind": "power",
        "seed": 0,
        "truth": truth,
        "predicted": predicted,
        "probabilities": None,
        "action": None,
        "jaccard": 1.0,
        "seconds_to_correct": 60.0 if predicted is truth else None,
        "false_dispatches": 0,
        "cost": 0.0,
        "api_calls": 0,
    }
    return Outcome(**{**base, **overrides})


# --- the systems on single runs


def test_engine_gets_a_clean_power_cut_right_and_fast():
    result = ENGINE(simulate("power", 1, QUIET))
    assert result.predicted is Cause.POWER
    assert result.action is Action.DISPATCH_POWER_CREW
    assert result.jaccard == 1.0
    assert result.seconds_to_correct <= 60
    assert result.false_dispatches == 0
    assert result.cost == 0


def test_engine_calls_a_listed_network_outage_and_waits():
    result = ENGINE(simulate("network", 1, QUIET))
    assert result.predicted is Cause.NETWORK
    assert result.action is Action.WAIT_FOR_NETWORK
    assert result.api_calls > 0


def test_engine_uses_location_verification_for_tamper():
    # Seed 0: the SIM turns up elsewhere 11 minutes in, inside the 15-minute window.
    result = ENGINE(simulate("tamper", 0, SimSettings(blips_per_hour=0, tamper_detect_rate=1.0)))
    assert result.predicted is Cause.TAMPER
    assert result.action is Action.INVESTIGATE_TAMPER


def test_b0_sends_a_technician_to_a_power_cut():
    run = simulate("power", 1, QUIET)
    result = B0(run)
    assert result.predicted is Cause.METER_FAULT
    assert result.false_dispatches == 1  # one job for the transformer, and it is the wrong one
    costs = DEFAULT_COSTS
    assert result.cost == costs.truck_roll + costs.late_power_per_meter * len(run.truth_meter_ids)
    assert result.api_calls == 0


def test_b1_waits_during_a_listed_outage_but_pays_in_api_calls():
    run = simulate("network", 1, QUIET)
    b0, b1 = B0(run), B1(run)
    assert b1.predicted is Cause.NETWORK
    assert b1.api_calls >= len(run.truth_meter_ids) * 0.8  # one call per silent meter
    assert b0.false_dispatches >= 2  # a technician per transformer for a Telstra problem
    assert b1.cost <= b0.cost


def test_baselines_chase_blips_unless_they_are_told_the_meter_came_back():
    run = simulate("meter_fault", 4, SimSettings(blips_per_hour=60, stale_outage_rate=0))
    today = B0(run)
    proposed = Baseline("B0", restore_events=True)(run)
    assert today.predicted is proposed.predicted is Cause.METER_FAULT
    assert today.false_dispatches > 5
    assert proposed.false_dispatches == 0
    assert proposed.seconds_to_correct > 900


def test_restore_events_stop_blips_muddying_the_real_fault():
    # A very noisy day: blips pile up around the one real meter fault (seed 5 on the real-suburb
    # layout; across seeds 0-11 restore events fix 7 runs and break none).
    run = simulate("meter_fault", 5, SimSettings(blips_per_hour=60, stale_outage_rate=0))
    today = ENGINE(run)
    proposed = EngineSystem(restore_events=True)(run)
    assert today.jaccard < 0.5 and not today.correct
    assert proposed.jaccard == 1.0 and proposed.correct


# --- metrics


def test_jaccard():
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert jaccard(set(), set()) == 1.0


def test_f1_per_cause_and_summary():
    outcomes = [
        outcome(Cause.POWER, Cause.POWER),
        outcome(Cause.POWER, Cause.NETWORK),
        outcome(Cause.NETWORK, Cause.NETWORK),
        outcome(Cause.NETWORK, None, jaccard=0.0),
    ]
    f1 = f1_per_cause(outcomes)
    assert f1[Cause.POWER] == 2 / 3  # precision 1, recall 1/2
    assert f1[Cause.NETWORK] == 0.5  # precision 1/2, recall 1/2
    assert Cause.TAMPER not in f1  # never happened, so not scored

    summary = summarise(outcomes)
    assert summary.accuracy == 0.5
    assert summary.never_correct == 0.5
    assert summary.median_seconds_to_correct == 60


def test_brier_rewards_honest_probabilities():
    sure_and_right = outcome(Cause.POWER, Cause.POWER, probabilities={Cause.POWER: 1.0})
    sure_and_wrong = outcome(Cause.POWER, Cause.NETWORK, probabilities={Cause.NETWORK: 1.0})
    missed = outcome(Cause.POWER, None)
    assert brier(sure_and_right) == 0
    assert brier(sure_and_wrong) == 2
    assert brier(missed) == 0.75


# --- the batch


def test_batch_runs_every_system_on_the_same_seeds_and_saves(tmp_path):
    outcomes = run_batch([ENGINE, B0, B1], seeds=range(3))
    assert len(outcomes) == 4 * 3 * 3  # kinds x seeds x systems
    assert outcomes == run_batch([ENGINE, B0, B1], seeds=range(3))  # repeatable

    summaries = write_results(tmp_path, outcomes)
    assert [s.system for s in summaries] == ["engine-v1", "B0", "B1"]

    with (tmp_path / "runs.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 36
    assert {"system", "kind", "seed", "truth", "predicted", "cost", "correct"} <= set(rows[0])

    saved = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert set(saved["accuracy_by_kind"]["engine-v1"]) == {
        "power", "network", "meter_fault", "tamper",
    }  # fmt: skip
    table = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "| engine-v1 |" in table and "Saved vs B0" in table
    assert results_table(summaries) in table

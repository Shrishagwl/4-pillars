from engine.contracts import Cause

from evaluation.metrics import summarise_by_system
from evaluation.runner import DEFAULT_SEEDS, run_batch
from evaluation.systems import EngineSystem
from evaluation.training import TRAIN_SEEDS, train_v2, training_examples, v2_system


def test_training_and_scoring_seeds_do_not_overlap():
    assert not set(TRAIN_SEEDS) & set(DEFAULT_SEEDS)


def test_examples_cover_every_cause_at_several_moments():
    examples = training_examples()
    causes = {cause for _, cause in examples}
    assert causes == set(Cause)
    assert len(examples) > 4 * len(TRAIN_SEEDS)  # more than one moment per run
    # Early examples exist: clusters that are still small or not yet listed.
    assert any(c.outage_share == 0 for c, cause in examples if cause is Cause.NETWORK)


def test_v2_beats_v1_on_held_out_runs():
    v1 = EngineSystem()
    v2 = v2_system(train_v2())
    outcomes = run_batch([v1, v2], seeds=range(20))
    scores = {s.system: s for s in summarise_by_system(outcomes)}

    assert scores["engine-v2"].accuracy > scores["engine-v1"].accuracy
    assert scores["engine-v2"].macro_f1 > scores["engine-v1"].macro_f1
    assert scores["engine-v2"].brier < scores["engine-v1"].brier


def test_dropping_location_costs_the_model_its_tamper_calls():
    full = v2_system(train_v2(), name="full")
    blind = v2_system(train_v2(drop=("location",)), name="blind")
    outcomes = run_batch([full, blind], seeds=range(10), kinds=["tamper"])
    hits = {s.system: s.accuracy for s in summarise_by_system(outcomes)}

    assert hits["full"] > 0.7
    # Only a small drop: in the twin most tampers also send a last gasp, and the SIM often
    # turns up somewhere else after the 15-minute window, when Location Verification is late.
    assert hits["blind"] < hits["full"]

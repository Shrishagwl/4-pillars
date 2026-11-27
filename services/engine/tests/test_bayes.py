import math

import pytest
from test_pipeline import NOW, TOPOLOGY, power_outage_on
from test_rules import PARTS_OF_MANY, WHOLE_TRANSFORMER, clues

from engine.bayes import FEATURES, NaiveBayes, featurise
from engine.contracts import Action, Cause, ReasonGroup
from engine.pipeline import assess

POWER = clues(**WHOLE_TRANSFORMER, outage_share=0.0)
NETWORK = clues(**PARTS_OF_MANY, outage_share=1.0)
METER = clues(outage_share=0.0, location_mismatch_share=0.0)
TAMPER = clues(outage_share=0.0, location_mismatch_share=1.0)

TRAINING = (
    [(POWER, Cause.POWER)] * 20
    + [(NETWORK, Cause.NETWORK)] * 20
    + [(METER, Cause.METER_FAULT)] * 20
    + [(TAMPER, Cause.TAMPER)] * 20
)
MODEL = NaiveBayes.fit(TRAINING)


def test_clues_become_named_buckets():
    features = featurise(POWER)
    assert features == {
        "size": "31+",
        "worst_transformer": "80%+",
        "spread_across": "1 transformer",
        "burst": "50-75%",
        "detached": "none",
        "duration": "2 min+",
        "outage": "not listed",
        "location": "not checked",
    }
    assert featurise(clues())["outage"] == "not checked"
    assert featurise(TAMPER)["location"] == "moved"


def test_every_bucket_a_feature_returns_is_declared():
    samples = [POWER, NETWORK, METER, TAMPER, clues(), clues(meter_count=4, burst_share=0.3)]
    for sample in samples:
        for name, bucket in featurise(sample).items():
            assert bucket in FEATURES[name][1]


@pytest.mark.parametrize(
    ("example", "cause"),
    [(POWER, Cause.POWER), (NETWORK, Cause.NETWORK), (METER, Cause.METER_FAULT),
     (TAMPER, Cause.TAMPER)],
)  # fmt: skip
def test_model_recognises_what_it_was_trained_on(example, cause):
    result = MODEL.score(example)
    assert result.cause is cause
    assert result.confidence > 0.9
    assert result.rule == "naive-bayes"
    assert set(result.probabilities) == set(Cause)
    assert sum(result.probabilities.values()) == pytest.approx(1.0)


def test_one_surprising_clue_lowers_confidence_but_does_not_flip_the_cause():
    # A power cut, except Telstra also lists an outage there.
    odd = clues(**WHOLE_TRANSFORMER, outage_share=1.0)
    result = MODEL.score(odd)
    assert result.cause is Cause.POWER
    assert result.confidence < MODEL.score(POWER).confidence


def test_smoothing_means_an_unseen_bucket_is_unlikely_but_not_impossible():
    # No training example of any cause had a "2-5" cluster.
    unseen = clues(meter_count=4, outage_share=0.0, location_mismatch_share=0.0)
    probabilities = MODEL.probabilities(unseen)
    assert all(p > 0 for p in probabilities.values())
    assert max(probabilities, key=probabilities.get) is Cause.METER_FAULT


def test_the_smoothed_probability_matches_the_formula_by_hand():
    # 20 power examples, all in bucket "31+" of a 4-bucket feature, alpha = 1:
    #   P("31+" | POWER) = (20 + 1) / (20 + 1 * 4) = 21/24
    #   P("1"   | POWER) = ( 0 + 1) / (20 + 1 * 4) =  1/24
    assert MODEL._log_likelihood(Cause.POWER, "size", "31+") == pytest.approx(math.log(21 / 24))
    assert MODEL._log_likelihood(Cause.POWER, "size", "1") == pytest.approx(math.log(1 / 24))


def test_reasons_name_the_clues_that_decided_it():
    result = MODEL.score(TAMPER)
    assert any(reason.startswith("location = moved") for reason in result.reasons)


def test_dropping_a_feature_makes_the_model_blind_to_it():
    blind = NaiveBayes.fit(TRAINING, drop=["location"])
    assert "location" not in featurise(TAMPER, blind.dropped)
    # Without location, a tamper and a meter fault look identical: a coin flip.
    assert blind.probabilities(TAMPER)[Cause.TAMPER] == pytest.approx(
        blind.probabilities(TAMPER)[Cause.METER_FAULT]
    )
    with pytest.raises(ValueError, match="unknown features"):
        NaiveBayes.fit(TRAINING, drop=["colour"])


def test_model_survives_saving_and_loading(tmp_path):
    path = tmp_path / "model.json"
    MODEL.save(path)
    loaded = NaiveBayes.load(path)
    assert loaded == MODEL
    assert loaded.probabilities(NETWORK) == MODEL.probabilities(NETWORK)


def test_training_on_nothing_is_an_error():
    with pytest.raises(ValueError, match="zero examples"):
        NaiveBayes.fit([])


def test_model_plugs_into_the_pipeline_in_place_of_the_rules():
    # Train on what the pipeline itself measures for a power cut and a lone meter.
    [power] = assess(power_outage_on("T5"), TOPOLOGY, NOW, outage_suburbs=set())
    lone = clues(outage_share=0.0, reason_shares={**dict.fromkeys(ReasonGroup, 0.0)})
    model = NaiveBayes.fit([(power.clues, Cause.POWER)] * 10 + [(lone, Cause.METER_FAULT)] * 10)

    [a] = assess(power_outage_on("T2"), TOPOLOGY, NOW, outage_suburbs=set(), scorer=model.score)

    assert a.result.cause is Cause.POWER
    assert a.result.rule == "naive-bayes"
    assert a.decision.action is Action.DISPATCH_POWER_CREW

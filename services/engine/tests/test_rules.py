import pytest

from engine.clues import Clues
from engine.contracts import Cause, ReasonGroup
from engine.rules import RuleThresholds, score_v1


def clues(**overrides) -> Clues:
    """A single silent meter by default; each test overrides what it cares about."""
    base = {
        "meter_count": 1,
        "transformer_count": 1,
        "suburb_count": 1,
        "transformer_share": 0.01,
        "max_transformer_share": 0.01,
        "suburb_share": 0.002,
        "spread_seconds": 0.0,
        "burst_share": 1.0,
        "reason_shares": dict.fromkeys(ReasonGroup, 0.0),
        "outage_share": None,
    }
    return Clues(**{**base, **overrides})


WHOLE_TRANSFORMER = {
    "meter_count": 80,
    "transformer_share": 0.95,
    "max_transformer_share": 0.95,
    "burst_share": 0.7,
    "spread_seconds": 240.0,
}
PARTS_OF_MANY = {
    "meter_count": 300,
    "transformer_count": 5,
    "transformer_share": 0.7,
    "max_transformer_share": 0.8,
    "burst_share": 0.1,
    "spread_seconds": 200.0,
}


def test_whole_transformer_dropping_fast_is_power():
    result = score_v1(clues(**WHOLE_TRANSFORMER))
    assert result.cause is Cause.POWER
    assert result.rule == "power"
    assert result.confidence == 0.9


def test_power_is_less_sure_when_telstra_also_lists_an_outage():
    result = score_v1(clues(**WHOLE_TRANSFORMER, outage_share=1.0))
    assert result.cause is Cause.POWER
    assert result.confidence == 0.6


def test_whole_transformer_dropping_slowly_is_not_power():
    result = score_v1(clues(**{**WHOLE_TRANSFORMER, "burst_share": 0.1}))
    assert result.cause is not Cause.POWER


def test_listed_outage_is_network():
    result = score_v1(clues(**PARTS_OF_MANY, outage_share=0.9))
    assert result.cause is Cause.NETWORK
    assert result.rule == "network-listed"
    assert result.confidence == 0.85


def test_network_pattern_without_a_listing_is_a_weak_network():
    not_checked = score_v1(clues(**PARTS_OF_MANY))
    checked_nothing = score_v1(clues(**PARTS_OF_MANY, outage_share=0.0))
    for result in (not_checked, checked_nothing):
        assert result.cause is Cause.NETWORK
        assert result.rule == "network-unlisted"
        assert result.confidence < 0.6  # low enough to go to manual review later


def test_single_meter_is_a_meter_fault():
    result = score_v1(clues())
    assert result.cause is Cause.METER_FAULT
    assert result.rule == "single-meter"


def test_single_meter_inside_a_listed_outage_is_network():
    result = score_v1(clues(outage_share=1.0))
    assert result.cause is Cause.NETWORK


def test_a_few_meters_on_one_transformer_is_unclear():
    result = score_v1(clues(meter_count=3, transformer_share=0.04, burst_share=0.3))
    assert result.rule == "unclear"
    assert result.confidence == 0.4


def test_probabilities_cover_every_cause_and_sum_to_one():
    result = score_v1(clues(**WHOLE_TRANSFORMER))
    assert set(result.probabilities) == set(Cause)
    assert sum(result.probabilities.values()) == pytest.approx(1.0)
    assert result.probabilities[Cause.POWER] == result.confidence
    assert max(result.probabilities, key=result.probabilities.get) is result.cause


def test_thresholds_can_be_changed():
    strict = RuleThresholds(power_transformer_share=0.99)
    assert score_v1(clues(**WHOLE_TRANSFORMER), strict).cause is not Cause.POWER


def test_one_stray_meter_does_not_hide_a_power_cut():
    # 100 of 100 on one transformer plus one meter on another: the average share is 50%.
    stray = {
        **WHOLE_TRANSFORMER,
        "meter_count": 101,
        "transformer_count": 2,
        "transformer_share": 0.5,
        "max_transformer_share": 1.0,
    }
    assert score_v1(clues(**stray)).cause is Cause.POWER


def test_two_meters_on_two_transformers_is_not_called_network():
    result = score_v1(clues(meter_count=2, transformer_count=2, burst_share=0.5))
    assert result.cause is Cause.METER_FAULT
    assert result.rule == "unclear"

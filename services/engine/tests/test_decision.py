import json

import pytest

from engine.contracts import Action, Cause
from engine.decision import RIGHT_ACTION, Costs, choose_action, expected_cost, load_costs

COSTS = Costs()


def sure_of(cause: Cause, confidence: float) -> dict[Cause, float]:
    rest = (1 - confidence) / 3
    return {c: confidence if c is cause else rest for c in Cause}


def test_right_action_costs_nothing():
    for cause, action in RIGHT_ACTION.items():
        assert COSTS.cost(action, cause, meters=50) == 0


def test_wrong_actions_cost_the_visit_plus_what_was_missed():
    # Crew sent during a Telstra outage: the visit is wasted, nothing else is lost.
    assert COSTS.cost(Action.DISPATCH_POWER_CREW, Cause.NETWORK, 200) == 800
    # Waiting during a power cut: no visit, but 200 customers stay off.
    assert COSTS.cost(Action.WAIT_FOR_NETWORK, Cause.POWER, 200) == 2000
    # Technician sent to a power cut: both.
    assert COSTS.cost(Action.DISPATCH_METER_TECH, Cause.POWER, 200) == 2300


def test_wrong_person_at_the_meter_costs_half_a_second_visit():
    assert COSTS.cost(Action.DISPATCH_METER_TECH, Cause.TAMPER, 1) == 150
    assert COSTS.cost(Action.INVESTIGATE_TAMPER, Cause.METER_FAULT, 1) == 150


def test_review_costs_the_operator_plus_a_share_of_the_delay():
    assert COSTS.cost(Action.MANUAL_REVIEW, Cause.NETWORK, 200) == 8
    assert COSTS.cost(Action.MANUAL_REVIEW, Cause.POWER, 200) == 8 + 0.1 * 2000


def test_expected_cost_is_the_weighted_average():
    probabilities = {Cause.POWER: 0.5, Cause.NETWORK: 0.5, Cause.METER_FAULT: 0, Cause.TAMPER: 0}
    # Waiting: half the time it is a power cut for 100 customers (1000), half the time free.
    assert expected_cost(Action.WAIT_FOR_NETWORK, probabilities, 100, COSTS) == 500


@pytest.mark.parametrize("cause", list(Cause))
def test_confident_verdict_gets_its_matching_action(cause):
    decision = choose_action(sure_of(cause, 0.9), meters=40)
    assert decision.action is RIGHT_ACTION[cause]
    assert set(decision.expected_costs) == set(RIGHT_ACTION.values())


def test_below_sixty_percent_goes_to_manual_review():
    decision = choose_action(sure_of(Cause.NETWORK, 0.55), meters=40)
    assert decision.action is Action.MANUAL_REVIEW
    assert "55%" in decision.reason


def test_exactly_sixty_percent_is_enough_to_act():
    assert choose_action(sure_of(Cause.POWER, 0.6), meters=40).action is not Action.MANUAL_REVIEW


def test_big_cluster_can_justify_a_crew_even_when_power_is_not_the_top_cause():
    # 70% network, but 30% chance that 2,000 customers are without power.
    probabilities = {Cause.NETWORK: 0.7, Cause.POWER: 0.3, Cause.METER_FAULT: 0, Cause.TAMPER: 0}
    assert choose_action(probabilities, meters=2000).action is Action.DISPATCH_POWER_CREW
    assert choose_action(probabilities, meters=20).action is Action.WAIT_FOR_NETWORK


def test_costs_load_from_json(tmp_path):
    path = tmp_path / "costs.json"
    path.write_text(json.dumps({"truck_roll": 350}), encoding="utf-8")
    assert load_costs(path).truck_roll == 350
    assert load_costs(path).power_crew == 800  # not in the file, keeps the default

    path.write_text(json.dumps({"truck_rol": 350}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown cost names"):
        load_costs(path)

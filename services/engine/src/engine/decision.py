"""Step 4 of the engine: pick the action that is cheapest on average.

We never know the cause for sure, only a probability for each one. So for every action we ask:
"if I do this, what does it cost under each possible cause, weighted by how likely that cause
is?" That weighted average is the expected cost, and we pick the action where it is lowest.

All costs are *avoidable* costs: the extra dollars compared with doing the right thing straight
away. The right action for the true cause therefore costs 0.

If we are less than 60% sure of the cause we do not act at all and send the incident to a
person (MANUAL_REVIEW).

The dollar values below come from task #8 (Set the cost of each decision). Sources and the
working for each number are in docs/decision-costs.md. Change both together.
"""

import json
from dataclasses import dataclass, fields
from pathlib import Path

from .contracts import Action, Cause

RIGHT_ACTION: dict[Cause, Action] = {
    Cause.POWER: Action.DISPATCH_POWER_CREW,
    Cause.NETWORK: Action.WAIT_FOR_NETWORK,
    Cause.METER_FAULT: Action.DISPATCH_METER_TECH,
    Cause.TAMPER: Action.INVESTIGATE_TAMPER,
}

# Actions the engine can choose between. MANUAL_REVIEW is not one of them: it is the
# fallback when the engine is not sure enough to choose.
REAL_ACTIONS: tuple[Action, ...] = tuple(RIGHT_ACTION.values())

DEFAULT_MIN_CONFIDENCE = 0.6


@dataclass(frozen=True, slots=True)
class Costs:
    """Dollars, ex GST, 2026. Sources and working: docs/decision-costs.md (#8)."""

    # One technician visit: Jemena's regulated "wasted site attendance" fee, business hours.
    truck_roll: float = 650.0
    # One power crew call-out: 2 field workers for 2 hours at Jemena's average BH/AH rate.
    power_crew: float = 1_200.0
    # A power cut we did not act on, per customer: AER value of customer reliability for
    # suburban Melbourne ($55.10/kWh) x 0.5 kW average household load x 1 hour extra delay.
    late_power_per_meter: float = 28.0
    # A faulty meter we did not send anyone to: two manual special reads until it is fixed.
    meter_left_broken: float = 125.0
    # Tampering we did not investigate: about six months of an average home's stolen power.
    missed_tamper: float = 600.0
    # Ten minutes of an operator at Jemena's administrative officer rate.
    manual_review: float = 20.0
    # A review delays the real action. We charge this share of the cost of doing nothing.
    review_delay_share: float = 0.1

    def visit(self, action: Action) -> float:
        """What it costs to send someone, whether or not they were needed."""
        if action is Action.DISPATCH_POWER_CREW:
            return self.power_crew
        if action in (Action.DISPATCH_METER_TECH, Action.INVESTIGATE_TAMPER):
            return self.truck_roll
        return 0.0

    def missed(self, cause: Cause, meters: int) -> float:
        """What it costs to leave this cause unhandled."""
        if cause is Cause.POWER:
            return self.late_power_per_meter * meters
        if cause is Cause.METER_FAULT:
            return self.meter_left_broken
        if cause is Cause.TAMPER:
            return self.missed_tamper
        return 0.0  # a network outage fixes itself

    def cost(self, action: Action, cause: Cause, meters: int) -> float:
        """Avoidable cost of taking `action` when the true cause is `cause`."""
        if action is Action.MANUAL_REVIEW:
            return self.manual_review + self.review_delay_share * self.missed(cause, meters)
        if action is RIGHT_ACTION[cause]:
            return 0.0
        on_site = {Action.DISPATCH_METER_TECH, Action.INVESTIGATE_TAMPER}
        if action in on_site and RIGHT_ACTION[cause] in on_site:
            # Someone is at the meter and will see the real problem, but it is the wrong
            # person for the job, so we charge half of a second visit.
            return self.truck_roll / 2
        return self.visit(action) + self.missed(cause, meters)


DEFAULT_COSTS = Costs()


def load_costs(path: Path) -> Costs:
    """Read costs from a JSON file like {"truck_roll": 350, "power_crew": 900}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Costs)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"unknown cost names in {path}: {sorted(unknown)}")
    return Costs(**data)


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    expected_costs: dict[Action, float]  # for the four real actions
    reason: str


def expected_cost(
    action: Action, probabilities: dict[Cause, float], meters: int, costs: Costs
) -> float:
    return sum(p * costs.cost(action, cause, meters) for cause, p in probabilities.items())


def choose_action(
    probabilities: dict[Cause, float],
    meters: int,
    costs: Costs = DEFAULT_COSTS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Decision:
    expected = {a: expected_cost(a, probabilities, meters, costs) for a in REAL_ACTIONS}
    top_cause = max(probabilities, key=probabilities.get)
    confidence = probabilities[top_cause]

    if confidence < min_confidence:
        return Decision(
            Action.MANUAL_REVIEW,
            expected,
            f"only {confidence:.0%} sure it is {top_cause}, below the {min_confidence:.0%} "
            "needed to act without a person",
        )

    # Cheapest wins. On a tie, prefer the action that matches the most likely cause.
    best = min(REAL_ACTIONS, key=lambda a: (expected[a], a is not RIGHT_ACTION[top_cause]))
    runner_up = min((a for a in REAL_ACTIONS if a is not best), key=expected.get)
    return Decision(
        best,
        expected,
        f"cheapest expected cost: ${expected[best]:,.0f} against ${expected[runner_up]:,.0f} "
        f"for {runner_up}",
    )

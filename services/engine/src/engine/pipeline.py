"""The engine's steps in one call: events -> clusters -> clues -> cause -> action.

Pure Python with no network or database, so the evaluation can run it thousands of times.
"""

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from datetime import datetime

from .clues import Clues, compute_clues
from .clustering import Cluster, cluster_silent_meters
from .contracts import MeterSilentEvent
from .decision import DEFAULT_COSTS, Costs, Decision, choose_action
from .rules import RuleResult, score_v1
from .topology import Topology

# Anything that turns clues into a cause with probabilities: the v1 rules or the v2 model.
Scorer = Callable[[Clues], RuleResult]


@dataclass(frozen=True, slots=True)
class Assessment:
    cluster: Cluster
    clues: Clues
    result: RuleResult
    decision: Decision


def assess(
    events: Iterable[MeterSilentEvent],
    topology: Topology,
    now: datetime,
    outage_suburbs: Collection[str] | None = None,
    *,
    scorer: Scorer = score_v1,
    costs: Costs = DEFAULT_COSTS,
) -> list[Assessment]:
    """One assessment per cluster of meters that went silent in the 15 minutes before `now`."""
    assessments = []
    for cluster in cluster_silent_meters(events, topology, now):
        clues = compute_clues(cluster, topology, outage_suburbs)
        result = scorer(clues)
        decision = choose_action(result.probabilities, cluster.size, costs)
        assessments.append(Assessment(cluster, clues, result, decision))
    return assessments

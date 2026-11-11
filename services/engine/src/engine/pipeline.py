"""The engine's steps in one call: events -> clusters -> clues -> cause -> action.

Pure Python with no network or database, so the evaluation can run it thousands of times.
"""

from collections.abc import Callable, Collection, Iterable, Mapping
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
class Signals:
    """What the engine knows at one moment besides the LoC events. None = not known."""

    # Network Availability: suburbs with a current outage.
    outage_suburbs: Collection[str] | None = None
    # Location Verification: SIMs that are not at their meter's address.
    moved_msisdns: Collection[str] | None = None
    # The next two do not exist in Telstra's API today. They are the two changes we propose,
    # and the evaluation switches them on to measure how much they would help.
    outage_msisdns: Collection[str] | None = None  # exact SIMs inside a listed outage area
    restored: Mapping[str, datetime] | None = None  # msisdn -> when it came back online


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
    signals: Signals | None = None,
    scorer: Scorer = score_v1,
    costs: Costs = DEFAULT_COSTS,
) -> list[Assessment]:
    """One assessment per cluster of meters that went silent in the 15 minutes before `now`.

    Pass either `outage_suburbs` on its own (the common case) or a full `signals`.
    """
    signals = signals or Signals(outage_suburbs=outage_suburbs)
    assessments = []
    for cluster in cluster_silent_meters(events, topology, now, restored=signals.restored):
        clues = compute_clues(
            cluster,
            topology,
            signals.outage_suburbs,
            outage_msisdns=signals.outage_msisdns,
            moved_msisdns=signals.moved_msisdns,
        )
        result = scorer(clues)
        decision = choose_action(result.probabilities, cluster.size, costs)
        assessments.append(Assessment(cluster, clues, result, decision))
    return assessments

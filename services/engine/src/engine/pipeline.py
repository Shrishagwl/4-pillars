"""The engine's three steps in one call: events -> clusters -> clues -> cause.

Pure Python with no network or database, so the evaluation can run it thousands of times.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime

from .clues import Clues, compute_clues
from .clustering import Cluster, cluster_silent_meters
from .contracts import MeterSilentEvent
from .rules import DEFAULT_THRESHOLDS, RuleResult, RuleThresholds, score_v1
from .topology import Topology


@dataclass(frozen=True, slots=True)
class Assessment:
    cluster: Cluster
    clues: Clues
    result: RuleResult


def assess(
    events: Iterable[MeterSilentEvent],
    topology: Topology,
    now: datetime,
    outage_suburbs: Collection[str] | None = None,
    thresholds: RuleThresholds = DEFAULT_THRESHOLDS,
) -> list[Assessment]:
    """One assessment per cluster of meters that went silent in the 15 minutes before `now`."""
    assessments = []
    for cluster in cluster_silent_meters(events, topology, now):
        clues = compute_clues(cluster, topology, outage_suburbs)
        assessments.append(Assessment(cluster, clues, score_v1(clues, thresholds)))
    return assessments

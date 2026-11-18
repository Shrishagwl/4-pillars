"""Step 2 of the engine: turn a cluster into clues (numbers the rules and the model can use).

Each clue is picked because the causes leave different fingerprints:

  POWER    one transformer loses nearly all its meters, most within seconds, many with a
           last-gasp code (DETACHED).
  NETWORK  many transformers each lose part of their meters over a few minutes, mostly
           DETECTION_TIMEOUT, and Telstra lists an outage for the suburb.
  METER    one meter, nothing else around it.

This module only measures. It does not decide anything; that is rules.py.
"""

from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from datetime import timedelta

from .clustering import Cluster
from .contracts import ReasonGroup, reason_group
from .topology import Topology

DEFAULT_BURST = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class Clues:
    meter_count: int
    transformer_count: int
    suburb_count: int
    # Silent meters / all meters on the transformers the cluster touches. 1.0 = all of them.
    transformer_share: float
    # Same, but for the single worst-hit transformer.
    max_transformer_share: float
    # Silent meters / all meters in the suburbs the cluster touches.
    suburb_share: float
    # Seconds between the first and the last drop.
    spread_seconds: float
    # Share of the cluster that dropped within `burst` of the first drop.
    burst_share: float
    # Share of the cluster per reason group; always has every group, and adds up to 1.
    reason_shares: dict[ReasonGroup, float]
    # Share of the cluster in a suburb where Telstra lists an outage.
    # None means the Outage API has not been asked yet, which is different from 0.0.
    outage_share: float | None

    @property
    def crosses_transformers(self) -> bool:
        return self.transformer_count > 1


def compute_clues(
    cluster: Cluster,
    topology: Topology,
    outage_suburbs: Collection[str] | None = None,
    burst: timedelta = DEFAULT_BURST,
) -> Clues:
    """Measure one cluster.

    `outage_suburbs` is the set of suburbs where Network Availability lists a current outage.
    Pass None when it has not been checked yet.
    """
    members = cluster.members
    count = len(members)

    silent_per_transformer = Counter(m.meter.transformer_id for m in members)
    total_on_transformers = sum(topology.meters_on_transformer(t) for t in silent_per_transformer)
    total_in_suburbs = sum(topology.meters_in_suburb(s) for s in cluster.suburbs)

    first = cluster.first_silent_at
    in_burst = sum(1 for m in members if m.silent_at - first <= burst)

    per_group = Counter(reason_group(m.reason_code) for m in members)

    outage_share = None
    if outage_suburbs is not None:
        outage_share = sum(1 for m in members if m.meter.suburb in outage_suburbs) / count

    return Clues(
        meter_count=count,
        transformer_count=len(silent_per_transformer),
        suburb_count=len(cluster.suburbs),
        transformer_share=count / total_on_transformers,
        max_transformer_share=max(
            silent / topology.meters_on_transformer(t)
            for t, silent in silent_per_transformer.items()
        ),
        suburb_share=count / total_in_suburbs,
        spread_seconds=(cluster.last_silent_at - first).total_seconds(),
        burst_share=in_burst / count,
        reason_shares={group: per_group[group] / count for group in ReasonGroup},
        outage_share=outage_share,
    )

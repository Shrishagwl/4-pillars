"""Step 2 of the engine: turn a cluster into clues (numbers the rules and the model can use).

Each clue is picked because the causes leave different fingerprints:

  POWER    one transformer loses nearly all its meters, most within seconds, many with a
           last-gasp code (DETACHED).
  NETWORK  many transformers each lose part of their meters over a few minutes, mostly
           DETECTION_TIMEOUT, and Telstra lists an outage for the suburb.
  METER    one meter, nothing else around it.
  TAMPER   one meter (or a couple), and Location Verification says the SIM has moved.

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
# Location Verification costs one API call per SIM, so we only ask for small clusters.
# A moved SIM explains one silent meter, not three hundred.
LOCATION_CHECK_MAX_METERS = 3


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
    # Biggest share of the cluster that dropped inside any one `burst`-long stretch (30 s).
    # Not "the first 30 s": one stray meter dropping earlier would hide a real burst.
    burst_share: float
    # Share of the cluster per reason group; always has every group, and adds up to 1.
    reason_shares: dict[ReasonGroup, float]
    # Share of the cluster in a suburb where Telstra lists an outage.
    # None means the Outage API has not been asked yet, which is different from 0.0.
    outage_share: float | None
    # Share of the cluster whose SIM is not where the meter is installed.
    # None means Location Verification was not asked (cluster too big, or not available).
    location_mismatch_share: float | None = None

    @property
    def crosses_transformers(self) -> bool:
        return self.transformer_count > 1


def compute_clues(
    cluster: Cluster,
    topology: Topology,
    outage_suburbs: Collection[str] | None = None,
    burst: timedelta = DEFAULT_BURST,
    *,
    outage_msisdns: Collection[str] | None = None,
    moved_msisdns: Collection[str] | None = None,
) -> Clues:
    """Measure one cluster.

    `outage_suburbs` is the set of suburbs where Network Availability lists a current outage.
    Pass None when it has not been checked yet.

    `outage_msisdns` is the more exact version: the SIMs inside the listed outage areas. When
    it is given it is used instead of the suburbs. Today's API only gives an area for some
    outages, so this is for testing the "outage shapes" API proposal.

    `moved_msisdns` is the set of SIMs that Location Verification says are not at their
    meter's address. Only looked at for clusters of up to LOCATION_CHECK_MAX_METERS.
    """
    members = cluster.members
    count = len(members)

    silent_per_transformer = Counter(m.meter.transformer_id for m in members)
    total_on_transformers = sum(topology.meters_on_transformer(t) for t in silent_per_transformer)
    total_in_suburbs = sum(topology.meters_in_suburb(s) for s in cluster.suburbs)

    first = cluster.first_silent_at
    # Slide a `burst`-long window over the drops (they are in time order) and keep the
    # fullest one. `start` is the oldest drop still inside the window that ends at `end`.
    in_burst = 0
    start = 0
    for end, member in enumerate(members):
        while member.silent_at - members[start].silent_at > burst:
            start += 1
        in_burst = max(in_burst, end - start + 1)

    per_group = Counter(reason_group(m.reason_code) for m in members)

    outage_share = None
    if outage_msisdns is not None:
        outage_share = sum(1 for m in members if m.meter.msisdn in outage_msisdns) / count
    elif outage_suburbs is not None:
        outage_share = sum(1 for m in members if m.meter.suburb in outage_suburbs) / count

    location_mismatch_share = None
    if moved_msisdns is not None and count <= LOCATION_CHECK_MAX_METERS:
        location_mismatch_share = sum(1 for m in members if m.meter.msisdn in moved_msisdns) / count

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
        location_mismatch_share=location_mismatch_share,
    )

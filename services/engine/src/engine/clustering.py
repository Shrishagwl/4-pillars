"""Step 1 of the engine: group silent meters into clusters (one cluster = one suspected incident).

Two silent meters end up in the same cluster when either is true:
  1. they share a transformer, or
  2. they are in the same suburb and went silent within `suburb_link_gap` of each other.

Links chain: if A links to B and B links to C, all three are one cluster. That is how a
suburb-wide network outage, where meters drop one after another, becomes a single cluster.

Rule 2 has a time limit and rule 1 does not, on purpose. A transformer is small, so two silent
meters on it in the same 15 minutes are almost certainly one event. A suburb is big, so two
unrelated meter faults can easily happen in it on the same day; they only count as one event
if they drop close together.
"""

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .contracts import MeterSilentEvent
from .topology import Meter, Topology

log = logging.getLogger(__name__)

DEFAULT_WINDOW = timedelta(minutes=15)
DEFAULT_SUBURB_LINK_GAP = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class SilentMeter:
    meter: Meter
    reason_code: int
    silent_at: datetime


@dataclass(frozen=True, slots=True)
class Cluster:
    cluster_id: str
    members: tuple[SilentMeter, ...]  # sorted by silent_at, then meter_id

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def transformer_ids(self) -> frozenset[str]:
        return frozenset(m.meter.transformer_id for m in self.members)

    @property
    def suburbs(self) -> frozenset[str]:
        return frozenset(m.meter.suburb for m in self.members)

    @property
    def first_silent_at(self) -> datetime:
        return self.members[0].silent_at

    @property
    def last_silent_at(self) -> datetime:
        return self.members[-1].silent_at


class _UnionFind:
    """Keeps track of which items are in the same group. union(a, b) merges two groups."""

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, i: int) -> int:
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]  # shorten the path as we go
            i = self._parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def _sort_key(member: SilentMeter) -> tuple[datetime, str]:
    return (member.silent_at, member.meter.meter_id)


def silent_meters_in_window(
    events: Iterable[MeterSilentEvent],
    topology: Topology,
    now: datetime,
    window: timedelta = DEFAULT_WINDOW,
) -> list[SilentMeter]:
    """Meters that went silent between `now - window` and `now`, one entry per meter.

    If a meter has several events in the window we keep the earliest (when it first dropped).
    Events for SIMs that are not in the topology are skipped.
    """
    earliest: dict[str, SilentMeter] = {}
    unknown = 0
    for event in events:
        if not (now - window <= event.eventTime <= now):
            continue
        meter = topology.get(event.msisdn)
        if meter is None:
            unknown += 1
            continue
        seen = earliest.get(meter.meter_id)
        if seen is None or event.eventTime < seen.silent_at:
            earliest[meter.meter_id] = SilentMeter(meter, event.reasonCode, event.eventTime)
    if unknown:
        log.warning("skipped events for unknown msisdns", extra={"count": unknown})
    return sorted(earliest.values(), key=_sort_key)


def cluster_silent_meters(
    events: Iterable[MeterSilentEvent],
    topology: Topology,
    now: datetime,
    window: timedelta = DEFAULT_WINDOW,
    suburb_link_gap: timedelta = DEFAULT_SUBURB_LINK_GAP,
) -> list[Cluster]:
    """Group the meters that went silent in the window. Returns clusters, earliest first."""
    silent = silent_meters_in_window(events, topology, now, window)
    groups = _UnionFind(len(silent))

    by_transformer: dict[str, list[int]] = defaultdict(list)
    by_suburb: dict[str, list[int]] = defaultdict(list)
    for i, member in enumerate(silent):
        by_transformer[member.meter.transformer_id].append(i)
        by_suburb[member.meter.suburb].append(i)

    # Rule 1: same transformer. Linking each meter to the first one joins them all.
    for indexes in by_transformer.values():
        for i in indexes[1:]:
            groups.union(indexes[0], i)

    # Rule 2: same suburb and close in time. `silent` is in time order, so comparing each
    # meter with the one just before it finds every chain.
    for indexes in by_suburb.values():
        for prev, cur in zip(indexes, indexes[1:], strict=False):
            if silent[cur].silent_at - silent[prev].silent_at <= suburb_link_gap:
                groups.union(prev, cur)

    members_by_root: dict[int, list[SilentMeter]] = defaultdict(list)
    for i, member in enumerate(silent):
        members_by_root[groups.find(i)].append(member)

    clusters = [
        Cluster(
            # Named after its lowest meter id, so the same incident keeps the same id
            # when the engine re-runs a moment later with a few more events.
            cluster_id="c-" + min(m.meter.meter_id for m in members),
            members=tuple(members),
        )
        for members in members_by_root.values()
    ]
    return sorted(clusters, key=lambda c: (c.first_silent_at, c.cluster_id))

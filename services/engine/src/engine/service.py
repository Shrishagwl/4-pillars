"""The engine as a running service: events in, incidents and verdicts out.

Every time events arrive (and every `tick` seconds, because incidents also change as time passes)
it re-scores everything in the window:

  1. find the clusters with no outside signals yet (cheap)
  2. ask telstra-gateway about those clusters (outages, moved SIMs)
  3. run the IncidentTracker with those signals
  4. write each incident and, when its verdict changed, a verdict row with a plain summary

Because each step re-scores the whole window, events that arrive late or out of order simply
land where they belong. Repeats are dropped by event id and by (SIM, time, reason).

On a restart it reads the recent events back from the database, replays them, and gives the
open incidents their old ids back, so the dashboard doesn't see them change.
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from .clustering import cluster_silent_meters
from .contracts import MeterSilentEvent
from .decision import DEFAULT_COSTS, Costs
from .gateway import Gateway
from .pipeline import Scorer, Signals
from .rules import score_v1
from .store import EngineStore
from .summary import Generate, with_summary
from .topology import Meter, Topology
from .tracker import Incident, IncidentTracker

log = logging.getLogger(__name__)

TopologyLoader = Callable[[], list[Meter]]
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class EngineService:
    def __init__(
        self,
        load_meters: TopologyLoader,
        store: EngineStore | None = None,
        gateway: Gateway | None = None,
        scorer: Scorer = score_v1,
        costs: Costs = DEFAULT_COSTS,
        generate: Generate | None = None,
        clock: Clock = utc_now,
        lookback: timedelta = timedelta(hours=2),
        topology_refresh: timedelta = timedelta(seconds=30),
    ) -> None:
        self._load_meters = load_meters
        self._store = store
        self._gateway = gateway
        self._scorer = scorer
        self._costs = costs
        self._generate = generate
        self._clock = clock
        self._lookback = lookback
        self._topology_refresh = topology_refresh
        self._lock = threading.Lock()  # FastAPI runs sync routes in a thread pool

        self._events: dict[tuple[str, datetime, int], MeterSilentEvent] = {}
        self._topology = Topology([])
        self._topology_loaded_at: float | None = None
        self._tracker = IncidentTracker(self._topology, scorer, costs)
        self._saved: dict[str, tuple] = {}  # incident id -> last verdict written
        self.incidents: list[Incident] = []

    # --- topology

    def _refresh_topology(self, force: bool = False) -> None:
        now = time.monotonic()
        recent = self._topology_loaded_at is not None and (
            now - self._topology_loaded_at < self._topology_refresh.total_seconds()
        )
        if recent and not force:
            return
        try:
            meters = self._load_meters()
        except Exception:  # noqa: BLE001  (ingest down: keep the old layout, try again later)
            log.warning("could not load the meter list", exc_info=True)
            return
        self._topology_loaded_at = now
        if len(meters) != len(self._topology):
            log.info("meter list loaded", extra={"meters": len(meters)})
        self._topology = Topology(meters)
        # Keep incident ids and numbering, only swap the layout underneath.
        self._tracker._topology = self._topology

    # --- events in

    def accept(self, events: list[MeterSilentEvent]) -> None:
        """The receiver's sink: store, remember and re-score."""
        with self._lock:
            if self._store is not None:
                events = self._store.add_events(events)
            added = 0
            for e in events:
                key = (e.msisdn, e.eventTime, e.reasonCode)
                if key not in self._events:
                    self._events[key] = e
                    added += 1
            if any(self._topology.get(e.msisdn) is None for e in events):
                self._refresh_topology()  # a SIM we don't know: the twin may have added meters
            if added:
                self._step()

    def tick(self) -> None:
        with self._lock:
            self._step()

    # --- restarts

    def rebuild(self) -> None:
        """Pick up where the last instance left off."""
        with self._lock:
            self._refresh_topology(force=True)
            if self._store is None:
                return
            now = self._clock()
            for e in self._store.events_since(now - self._lookback):
                self._events[(e.msisdn, e.eventTime, e.reasonCode)] = e
            highest = self._store.highest_incident_number()
            self._tracker._next_number = highest + 1
            open_before = self._store.open_incidents()
            self._step(adopt=open_before)
            # The replay numbered its incidents before they took their old ids back; carry on
            # from the highest number actually in use so no numbers are skipped.
            in_use = [int(i.incident_id.rsplit("-", 1)[-1]) for i in self.incidents]
            self._tracker._next_number = max([highest, *in_use]) + 1
            log.info(
                "rebuilt from the database",
                extra={"events": len(self._events), "open": len(self.incidents)},
            )

    # --- the work

    def _step(self, adopt: dict[str, frozenset[str]] | None = None) -> None:
        now = self._clock()
        cutoff = now - self._lookback
        self._events = {k: e for k, e in self._events.items() if e.eventTime >= cutoff}
        events = list(self._events.values())

        signals = Signals()
        if self._gateway is not None:
            clusters = cluster_silent_meters(events, self._topology, now)
            if clusters:
                ids = self._incident_ids_for(clusters)
                signals = self._gateway.signals(clusters, ids)

        open_before = {i.incident_id for i in self._tracker.open}
        self.incidents = self._tracker.update(events, now, signals)

        if adopt:
            self._adopt_ids(adopt)

        if self._store is None:
            return
        for incident in self.incidents:
            self._save(incident, now)
        still_open = {i.incident_id for i in self.incidents}
        for incident in self._tracker.closed:
            if incident.incident_id in open_before and incident.incident_id not in still_open:
                self._store.close_incident(incident.incident_id, now)
                self._saved.pop(incident.incident_id, None)
        if adopt:
            # Open in the database but nothing in the replay matched it: it aged out while
            # we were down.
            adopted = {i.incident_id for i in self.incidents}
            for incident_id in adopt.keys() - adopted:
                self._store.close_incident(incident_id, now)

    def _incident_ids_for(self, clusters) -> dict[str, str]:
        """Tag gateway calls with the incident a cluster belongs to, for the gateway's logs."""
        ids = {}
        for cluster in clusters:
            meters = {m.meter.meter_id for m in cluster.members}
            best = max(self._tracker.open, key=lambda i: len(i.meter_ids & meters), default=None)
            if best is not None and best.meter_ids & meters:
                ids[cluster.cluster_id] = best.incident_id
        return ids

    def _adopt_ids(self, before: dict[str, frozenset[str]]) -> None:
        free = dict(before)
        for incident in self.incidents:
            best = max(free, key=lambda i: len(free[i] & incident.meter_ids), default=None)
            if best is not None and free[best] & incident.meter_ids:
                incident.incident_id = best
                del free[best]

    def _save(self, incident: Incident, now: datetime) -> None:
        a = incident.assessment
        cluster = a.cluster
        self._store.save_incident(
            incident.incident_id,
            cluster.members[0].silent_at,
            now,
            None,
            sorted(incident.meter_ids),
            sorted(cluster.transformer_ids),
            sorted(cluster.suburbs),
        )
        fingerprint = (
            a.result.cause,
            a.decision.action,
            round(a.result.confidence, 2),
            cluster.size,
        )
        if self._saved.get(incident.incident_id) == fingerprint:
            return
        verdict = with_summary(incident.verdict(now), self._generate)
        self._store.add_verdict(verdict)
        self._saved[incident.incident_id] = fingerprint
        log.info(
            "verdict",
            extra={
                "incidentId": incident.incident_id,
                "cause": verdict.cause.value,
                "confidence": round(verdict.confidence, 3),
                "action": verdict.action.value,
                "meters": verdict.meterCount,
            },
        )

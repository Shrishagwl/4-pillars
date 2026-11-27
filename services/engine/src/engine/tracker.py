"""Step 6 of the engine: keep incidents alive between runs and record why a verdict changed.

`assess` is a snapshot: give it the events so far and it tells you what it sees right now. Run
it again a minute later and it knows nothing about the minute before. The tracker is the
memory on top: it gives each incident an id that stays the same as the cluster grows, and it
keeps a history line every time the cause, the action or the confidence changes.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .clustering import DEFAULT_WINDOW
from .contracts import Action, Cause, MeterSilentEvent, Verdict
from .decision import DEFAULT_COSTS, Costs
from .evidence import to_verdict
from .pipeline import Assessment, Scorer, Signals, assess, assess_cluster
from .rules import score_v1
from .topology import Topology


@dataclass(frozen=True, slots=True)
class Change:
    at: datetime
    cause: Cause
    confidence: float
    action: Action
    why: str


@dataclass(slots=True)
class Incident:
    incident_id: str
    opened_at: datetime
    assessment: Assessment
    history: list[Change] = field(default_factory=list)
    closed_at: datetime | None = None

    @property
    def meter_ids(self) -> frozenset[str]:
        return frozenset(m.meter.meter_id for m in self.assessment.cluster.members)

    def verdict(self, now: datetime) -> Verdict:
        a = self.assessment
        return to_verdict(self.incident_id, a.cluster, a.clues, a.result, a.decision, now)


def _outage_state(share: float | None) -> str:
    if share is None:
        return "not checked"
    return "listed" if share > 0 else "not listed"


def explain_change(old: Assessment, new: Assessment) -> str:
    """Plain-English reasons the new assessment differs from the old one."""
    reasons = []
    if new.clues.meter_count != old.clues.meter_count:
        reasons.append(f"silent meters {old.clues.meter_count} -> {new.clues.meter_count}")
    if new.clues.transformer_count != old.clues.transformer_count:
        reasons.append(
            f"transformers touched {old.clues.transformer_count} -> {new.clues.transformer_count}"
        )
    before, after = _outage_state(old.clues.outage_share), _outage_state(new.clues.outage_share)
    if before != after:
        reasons.append(f"Outage API {before} -> {after}")
    if new.clues.location_mismatch_share != old.clues.location_mismatch_share:
        reasons.append("Location Verification result changed")
    if new.result.rule != old.result.rule:
        reasons.append(f"rule '{old.result.rule}' -> '{new.result.rule}'")
    return "; ".join(reasons) or "clues shifted"


class IncidentTracker:
    def __init__(
        self,
        topology: Topology,
        scorer: Scorer = score_v1,
        costs: Costs = DEFAULT_COSTS,
    ) -> None:
        self._topology = topology
        self._scorer = scorer
        self._costs = costs
        self._next_number = 1
        self.open: list[Incident] = []
        self.closed: list[Incident] = []

    def update(
        self,
        events: Iterable[MeterSilentEvent],
        now: datetime,
        signals: Signals | None = None,
    ) -> list[Incident]:
        """Re-score with everything known at `now`. Returns the incidents that are open."""
        assessments = assess(
            events,
            self._topology,
            now,
            signals=signals or Signals(),
            scorer=self._scorer,
            costs=self._costs,
        )

        still_open: list[Incident] = []
        unclaimed = list(self.open)
        for assessment in assessments:
            meter_ids = {m.meter.meter_id for m in assessment.cluster.members}
            # Same incident as before = the open incident it shares the most meters with.
            match = max(unclaimed, key=lambda i: len(i.meter_ids & meter_ids), default=None)
            if match is None or not (match.meter_ids & meter_ids):
                incident = Incident(f"inc-{self._next_number:04d}", now, assessment)
                self._next_number += 1
                self._record(incident, now, "incident opened")
            else:
                unclaimed.remove(match)
                incident = match
                old = incident.assessment
                if self._winding_down(old, meter_ids, now):
                    # Keep the whole cluster, but still listen to the APIs: a tamper's SIM
                    # can turn up somewhere else long after the meter went quiet.
                    assessment = assess_cluster(
                        old.cluster, self._topology, signals or Signals(), self._scorer, self._costs
                    )
                incident.assessment = assessment
                if self._verdict_changed(old, assessment):
                    self._record(incident, now, explain_change(old, assessment))
            still_open.append(incident)

        # Whatever was open and no longer shows up has aged out of the 15-minute window
        # (or its meters came back).
        for incident in unclaimed:
            incident.closed_at = now
            self.closed.append(incident)
        self.open = still_open
        return still_open

    @staticmethod
    def _winding_down(old: Assessment, meter_ids: set[str], now: datetime) -> bool:
        """True when the cluster only shrank because its first meters aged out of the window.

        Without this, a power cut slowly turns into a "meter fault": the last-gasp meters drop
        out of the 15-minute window first, and the last few timed-out meters left behind look
        like one broken meter. Nothing new was learned about the meters, so the incident keeps
        all of them until it closes. Meters that came back (a restore) are recent, so they don't
        count here.
        """
        gone = [m for m in old.cluster.members if m.meter.meter_id not in meter_ids]
        old_ids = {m.meter.meter_id for m in old.cluster.members}
        aged_out = now - DEFAULT_WINDOW
        return bool(gone) and meter_ids <= old_ids and all(m.silent_at < aged_out for m in gone)

    @staticmethod
    def _verdict_changed(old: Assessment, new: Assessment) -> bool:
        return (
            new.result.cause is not old.result.cause
            or new.decision.action is not old.decision.action
            or abs(new.result.confidence - old.result.confidence) >= 0.01
        )

    @staticmethod
    def _record(incident: Incident, now: datetime, why: str) -> None:
        a = incident.assessment
        incident.history.append(
            Change(now, a.result.cause, a.result.confidence, a.decision.action, why)
        )

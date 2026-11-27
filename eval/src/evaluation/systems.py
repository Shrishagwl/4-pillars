"""The things we compare on the same runs: our engine and two simple baselines.

Each system is a callable: give it a Run, get back an Outcome (what it decided and what that
cost, scored against the run's answer key).

  engine  watches the events arrive, re-scoring every 30 s (v1 rules or the v2 model)
  B0      sends a technician to any meter silent for 15 minutes, one job per transformer
  B1      same, but first asks the Outage API about each silent meter's suburb and waits
          instead if an outage is listed
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.clues import LOCATION_CHECK_MAX_METERS
from engine.contracts import Action, Cause
from engine.decision import DEFAULT_COSTS, RIGHT_ACTION, Costs
from engine.pipeline import Scorer, Signals
from engine.rules import score_v1
from engine.tracker import Incident, IncidentTracker

from .sim import Run

DISPATCHES = frozenset(
    {Action.DISPATCH_POWER_CREW, Action.DISPATCH_METER_TECH, Action.INVESTIGATE_TAMPER}
)
BASELINE_GAP = timedelta(minutes=15)


@dataclass(frozen=True)
class Outcome:
    system: str
    kind: str
    seed: int
    truth: Cause
    predicted: Cause | None  # None = the system never noticed the fault
    probabilities: dict[Cause, float] | None
    action: Action | None
    jaccard: float  # overlap between the meters it blamed and the meters really affected
    seconds_to_correct: float | None  # from the fault until the verdict was right for good
    false_dispatches: int
    cost: float  # avoidable dollars, from the engine's cost table
    api_calls: int

    @property
    def correct(self) -> bool:
        return self.predicted is self.truth


def jaccard(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 1.0


def _main_incident(incidents: list[Incident], truth_ids: frozenset[str]) -> Incident | None:
    """The incident that shares the most meters with the real fault, if any does."""
    best = max(incidents, key=lambda i: len(i.meter_ids & truth_ids), default=None)
    return best if best is not None and best.meter_ids & truth_ids else None


@dataclass(frozen=True)
class EngineSystem:
    name: str = "engine-v1"
    scorer: Scorer = score_v1
    costs: Costs = DEFAULT_COSTS
    # The two API changes we propose to Telstra. Off = the API as it is today.
    outage_shapes: bool = False
    restore_events: bool = False
    step_s: int = 30

    def signals(self, run: Run, now: datetime) -> Signals:
        return Signals(
            outage_suburbs=run.outage_suburbs_at(now),
            moved_msisdns=run.moved_msisdns_at(now),
            outage_msisdns=run.outage_msisdns_at(now) if self.outage_shapes else None,
            restored=run.restores if self.restore_events else None,
        )

    def __call__(self, run: Run) -> Outcome:
        tracker = IncidentTracker(run.grid.topology, self.scorer, self.costs)
        outage_calls: set[tuple[str, int]] = set()  # the gateway caches a suburb for a minute
        location_calls: set[str] = set()
        correct_since: datetime | None = None
        incidents: list[Incident] = []

        now = run.start
        while now < run.end:
            now = min(now + timedelta(seconds=self.step_s), run.end)
            incidents = tracker.update(run.events_until(now), now, self.signals(run, now))

            minute = int((now - run.start).total_seconds() // 60)
            for incident in incidents:
                cluster = incident.assessment.cluster
                outage_calls.update((suburb, minute) for suburb in cluster.suburbs)
                if cluster.size <= LOCATION_CHECK_MAX_METERS:
                    location_calls.update(m.meter.msisdn for m in cluster.members)

            main = _main_incident(incidents, run.truth_meter_ids)
            # Once the fault ages out of the 15-minute window there is no open incident for it.
            # That is not a wrong verdict, so only a wrong verdict resets the clock.
            if main is not None:
                if main.assessment.result.cause is run.truth:
                    correct_since = correct_since or now
                else:
                    correct_since = None

        # Incidents that aged out keep their last verdict and action, so they count too.
        incidents = [*tracker.closed, *incidents]
        main = _main_incident(incidents, run.truth_meter_ids)
        meters = len(run.truth_meter_ids)
        cost = 0.0
        false_dispatches = 0
        for incident in incidents:
            action = incident.assessment.decision.action
            if incident is main:
                cost += self.costs.cost(action, run.truth, meters)
                wrong = action is not RIGHT_ACTION[run.truth]
            else:
                # Not the real fault: a blip, or a stray piece of it. Any visit is wasted.
                cost += self.costs.visit(action)
                if action is Action.MANUAL_REVIEW:
                    cost += self.costs.manual_review
                wrong = True
            if wrong and action in DISPATCHES:
                false_dispatches += 1
        if main is None:
            cost += self.costs.missed(run.truth, meters)

        return Outcome(
            system=self.name,
            kind=run.kind,
            seed=run.seed,
            truth=run.truth,
            predicted=main.assessment.result.cause if main else None,
            probabilities=main.assessment.result.probabilities if main else None,
            action=main.assessment.decision.action if main else None,
            jaccard=jaccard(main.meter_ids, run.truth_meter_ids) if main else 0.0,
            seconds_to_correct=(
                (correct_since - run.fault_at).total_seconds() if correct_since else None
            ),
            false_dispatches=false_dispatches,
            cost=cost,
            api_calls=len(outage_calls) + len(location_calls),
        )


@dataclass(frozen=True)
class Baseline:
    """B0 and B1. They work per meter and act once a meter has been silent for 15 minutes."""

    name: str = "B0"
    check_outage_api: bool = False  # True = B1
    costs: Costs = DEFAULT_COSTS
    # Same switch as the engine has, so the comparison is fair: with today's API nobody is
    # told that a meter came back, so the baselines chase blips too.
    restore_events: bool = False

    def __call__(self, run: Run) -> Outcome:
        by_msisdn = {m.msisdn: m for m in run.grid.meters}
        # Meters silent for 15 minutes. With restore events, meters that came back drop out.
        silent = {}
        for event in run.events:
            back_at = run.restores.get(event.msisdn) if self.restore_events else None
            decided_at = event.eventTime + BASELINE_GAP
            # Only what it would do while we are watching, the same as the engine.
            if decided_at <= run.end and (back_at is None or back_at > decided_at):
                silent.setdefault(event.msisdn, decided_at)

        # Label every silent meter: NETWORK if B1 finds an outage listed for its suburb,
        # otherwise METER_FAULT.
        labels: dict[str, Cause] = {}
        for msisdn, decided_at in silent.items():
            listed = self.check_outage_api and (
                by_msisdn[msisdn].suburb in run.outage_suburbs_at(decided_at)
            )
            labels[by_msisdn[msisdn].meter_id] = Cause.NETWORK if listed else Cause.METER_FAULT
        api_calls = len(silent) if self.check_outage_api else 0

        # One technician job per transformer that has a meter labelled METER_FAULT.
        transformer_of = {m.meter_id: m.transformer_id for m in run.grid.meters}
        job_transformers = {
            transformer_of[mid] for mid, label in labels.items() if label is Cause.METER_FAULT
        }
        truth_transformers = {transformer_of[mid] for mid in run.truth_meter_ids}
        jobs_on_fault = len(job_transformers & truth_transformers)
        jobs_elsewhere = len(job_transformers - truth_transformers)

        blamed = frozenset(labels)
        seen = blamed & run.truth_meter_ids
        meters = len(run.truth_meter_ids)
        tech = Action.DISPATCH_METER_TECH

        if not seen:
            predicted, action = None, None
            cost = self.costs.missed(run.truth, meters)
            false_dispatches = 0
        else:
            predicted = Counter(labels[mid] for mid in seen).most_common(1)[0][0]
            action = tech if predicted is Cause.METER_FAULT else Action.WAIT_FOR_NETWORK
            cost = self.costs.cost(action, run.truth, meters)
            # The cost table covers one visit. Extra jobs on the same fault are extra visits.
            extra_jobs = jobs_on_fault - (1 if action is tech else 0)
            cost += extra_jobs * self.costs.visit(tech)
            false_dispatches = jobs_on_fault if RIGHT_ACTION[run.truth] is not tech else extra_jobs
        cost += jobs_elsewhere * self.costs.visit(tech)
        false_dispatches += jobs_elsewhere

        first_decision = min(
            (at for msisdn, at in silent.items() if by_msisdn[msisdn].meter_id in seen),
            default=None,
        )
        return Outcome(
            system=self.name,
            kind=run.kind,
            seed=run.seed,
            truth=run.truth,
            predicted=predicted,
            probabilities={c: 1.0 if c is predicted else 0.0 for c in Cause} if predicted else None,
            action=action,
            jaccard=jaccard(blamed, run.truth_meter_ids),
            seconds_to_correct=(
                (first_decision - run.fault_at).total_seconds()
                if predicted is run.truth and first_decision
                else None
            ),
            false_dispatches=false_dispatches,
            cost=cost,
            api_calls=api_calls,
        )


B0 = Baseline("B0")
B1 = Baseline("B1", check_outage_api=True)

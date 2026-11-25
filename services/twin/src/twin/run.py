"""Play a scenario on the twin and collect what happened (#18, used by #32 and the eval).

    from twin.run import run_scenario
    from twin.scenario import load_scenario
    result = run_scenario(load_scenario("scenarios/power-outage.yaml"), seed=1)
    result.loc_reports   # what the engine gets to see
    result.answer_key    # the truth, kept separate so the engine can never peek at it

The run's seed decides everything random about the run: which target "random" picks, when each
meter drops, which ones send a last gasp. The twin's layout comes from the scenario's own
twin_seed, so every run of a scenario plays out on the same map.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clock import DEFAULT_START, Heartbeat, TwinClock
from .faults import LocReport, power_outage, restore_power
from .grid import build_twin
from .scenario import Cause, Scenario, ScheduledFault, schedule

# What each fault kind does when it starts, and when it is fixed. The other kinds are added by
# their own issues; until then a scenario that uses them fails with a clear message.
START: dict[str, Callable[[ScheduledFault, TwinClock, random.Random], list[LocReport]]] = {
    "power": power_outage,
}
RESTORE: dict[str, Callable[[ScheduledFault, TwinClock], None]] = {
    "power": restore_power,
}
COMING_IN = {"network": "#21", "meter": "#28", "tamper": "#31"}


@dataclass(frozen=True, slots=True)
class Incident:
    """One line of the answer key: what really happened."""

    incident_id: str
    cause: Cause
    target: str  # the transformer, suburb or meter that failed
    started_at: datetime
    restored_at: datetime | None  # None if it was still broken when the run ended
    meter_ids: tuple[str, ...]  # every meter in the target, whether or not it reported


@dataclass(frozen=True, slots=True)
class RunResult:
    scenario: str
    seed: int
    twin_seed: int
    loc_reports: tuple[LocReport, ...]  # sorted by event_time
    heartbeats: tuple[Heartbeat, ...]
    answer_key: tuple[Incident, ...]


def run_scenario(scenario: Scenario, seed: int, start: datetime = DEFAULT_START) -> RunResult:
    twin = build_twin(scenario.twin_seed)
    clock = TwinClock(twin, start)
    # A label plus the seed, so this generator never shares numbers with the twin's or the
    # clock's (the same idea as the clock's heartbeat slots).
    rng = random.Random(f"run:{scenario.name}:{seed}")
    planned = schedule(scenario, twin, rng)

    for p in planned:
        if p.fault.kind not in START:
            raise NotImplementedError(
                f"{scenario.name}: '{p.fault.kind}' faults arrive in {COMING_IN[p.fault.kind]}"
            )

    reports: list[LocReport] = []
    heartbeats: list[Heartbeat] = []
    for minute in range(scenario.duration_min):
        # Restores first, then new faults, so a fault and a repair on the same minute behave.
        for p in planned:
            if p.restore_at_min == minute:
                RESTORE[p.fault.kind](p, clock)
        for p in planned:
            if p.at_min == minute:
                reports += START[p.fault.kind](p, clock, rng)
        heartbeats += clock.step()

    answer_key = tuple(
        Incident(
            incident_id=f"{scenario.name}-{seed}-{i + 1}",
            cause=p.fault.cause,
            target=p.target,
            started_at=start + timedelta(minutes=p.at_min),
            restored_at=(
                start + timedelta(minutes=p.restore_at_min)
                if p.restore_at_min is not None and p.restore_at_min < scenario.duration_min
                else None
            ),
            meter_ids=p.meter_ids,
        )
        for i, p in enumerate(planned)
    )
    return RunResult(
        scenario=scenario.name,
        seed=seed,
        twin_seed=scenario.twin_seed,
        loc_reports=tuple(sorted(reports, key=lambda r: (r.event_time, r.msisdn))),
        heartbeats=tuple(heartbeats),
        answer_key=answer_key,
    )

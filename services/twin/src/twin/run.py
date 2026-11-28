"""Play a scenario on the twin and collect what happened (#18, used by #32 and the eval).

    from twin.run import run_scenario
    from twin.scenario import load_scenario
    result = run_scenario(load_scenario("scenarios/power-outage.yaml"), seed=1)
    result.loc_reports   # what the engine gets to see
    result.outages       # what Telstra's Network Availability API lists, and from when
    result.answer_key    # the truth, kept separate so the engine can never peek at it
    result.background    # normal-day dropouts: also truth, and not incidents
    result.relocations   # where tampered SIMs turned up (what Location Verification would see)

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
from .faults import (
    LocReport,
    OutageNotice,
    Relocation,
    meter_failure,
    network_outage,
    power_outage,
    restore_meter,
    restore_network,
    restore_power,
    tamper_reappear,
    tamper_removal,
    timeout_code,
)
from .grid import build_twin
from .scenario import Cause, NetworkFault, Noise, Scenario, ScheduledFault, TamperFault, schedule

# What each fault kind does when it starts, and when it is fixed. A tampered meter is never
# fixed in place; instead its SIM reappears somewhere else (see run_scenario).
START: dict[str, Callable[[ScheduledFault, TwinClock, random.Random], list[LocReport]]] = {
    "power": power_outage,
    "network": network_outage,
    "meter": meter_failure,
    "tamper": tamper_removal,
}
RESTORE: dict[str, Callable[[ScheduledFault, TwinClock], None]] = {
    "power": restore_power,
    "network": restore_network,
    "meter": restore_meter,
}


@dataclass(frozen=True, slots=True)
class Incident:
    """One line of the answer key: what really happened."""

    incident_id: str
    cause: Cause
    target: str  # the transformer, suburb or meter that failed
    started_at: datetime
    restored_at: datetime | None  # None if it was still broken when the run ended
    # The meters this fault actually took offline. For a power cut that is the whole
    # transformer; for a network outage only the 60-90% of the suburb that lost signal.
    meter_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Dropout:
    """One background dropout (#28): a meter loses signal and comes back by itself. Not an
    incident, so it is not in the answer key. A good engine sends nobody for these."""

    meter_id: str
    msisdn: str
    dropped_at: datetime
    back_at: datetime | None  # None if it was still out when the run ended
    reported: bool  # it lasted past the detection timer, so Telstra sent a code 7


@dataclass(frozen=True, slots=True)
class RunResult:
    scenario: str
    seed: int
    twin_seed: int
    loc_reports: tuple[LocReport, ...]  # sorted by event_time
    outages: tuple[OutageNotice, ...]  # only those listed before the run ended
    heartbeats: tuple[Heartbeat, ...]
    answer_key: tuple[Incident, ...]
    background: tuple[Dropout, ...] = ()
    relocations: tuple[Relocation, ...] = ()

    def moved_msisdns(self, at: datetime) -> set[str]:
        """SIMs that are online away from their meter's address at time `at`: the ones
        Location Verification would answer FALSE for. This is the engine's moved_msisdns."""
        return {r.msisdn for r in self.relocations if r.moved_at <= at}


def run_scenario(scenario: Scenario, seed: int, start: datetime = DEFAULT_START) -> RunResult:
    twin = build_twin(scenario.twin_seed)
    clock = TwinClock(twin, start)
    # A label plus the seed, so this generator never shares numbers with the twin's or the
    # clock's (the same idea as the clock's heartbeat slots).
    rng = random.Random(f"run:{scenario.name}:{seed}")
    # Background noise gets its own generator, so switching noise on or off never changes
    # which transformer a fault hits or when.
    noise_rng = random.Random(f"noise:{scenario.name}:{seed}")
    planned = schedule(scenario, twin, rng)

    meter_of = {m.msisdn: m.meter_id for m in twin.meters}
    msisdn_of = {m.meter_id: m.msisdn for m in twin.meters}
    postcode_of = {s.name: s.postcode for s in twin.suburbs}
    end = start + timedelta(minutes=scenario.duration_min)

    def at(minute: int | None) -> datetime | None:
        return None if minute is None else start + timedelta(minutes=minute)

    def restored_at(p: ScheduledFault) -> datetime | None:
        when = at(p.restore_at_min)
        return when if when is not None and when < end else None

    reports: list[LocReport] = []
    outages: list[OutageNotice] = []
    heartbeats: list[Heartbeat] = []
    background: list[Dropout] = []
    relocations: list[Relocation] = []
    reappear: dict[int, list[ScheduledFault]] = {}  # minute -> tampered meters coming back
    reconnect: dict[int, list[str]] = {}  # minute -> meters whose dropout ends then
    silenced: dict[int, tuple[str, ...]] = {}
    for minute in range(scenario.duration_min):
        # Repairs and reconnections first, then new faults, so a fault and a repair on the
        # same minute behave.
        clock.set_connected(reconnect.pop(minute, []), True)
        for p in reappear.pop(minute, []):
            relocations.append(tamper_reappear(p, clock, rng))
        for p in planned:
            if p.restore_at_min == minute:
                RESTORE[p.fault.kind](p, clock)
        for i, p in enumerate(planned):
            if p.at_min != minute:
                continue
            new = START[p.fault.kind](p, clock, rng)
            reports += new
            silenced[i] = tuple(sorted(meter_of[r.msisdn] for r in new))
            if isinstance(p.fault, TamperFault) and new:
                back = minute + rng.randint(*p.fault.reappear_after_min)
                reappear.setdefault(back, []).append(p)
            if isinstance(p.fault, NetworkFault):
                listed_at = clock.now + timedelta(minutes=rng.randint(*p.fault.notice_lag_min))
                if listed_at < end:
                    outages.append(
                        OutageNotice(
                            p.target, postcode_of[p.target], clock.now, listed_at, restored_at(p)
                        )
                    )
        if scenario.noise is not None:
            dropout = _maybe_drop_out(scenario.noise, clock, noise_rng, minute, end)
            if dropout is not None:
                meter_id, back_minute, report, record = dropout
                reconnect.setdefault(back_minute, []).append(meter_id)
                background.append(record(msisdn_of[meter_id]))
                if report is not None:
                    reports.append(
                        LocReport(msisdn_of[meter_id], timeout_code(msisdn_of[meter_id]), report)
                    )
        heartbeats += clock.step()

    answer_key = tuple(
        Incident(
            incident_id=f"{scenario.name}-{seed}-{i + 1}",
            cause=p.fault.cause,
            target=p.target,
            started_at=at(p.at_min),
            restored_at=restored_at(p),
            meter_ids=silenced[i],
        )
        for i, p in enumerate(planned)
    )
    return RunResult(
        scenario=scenario.name,
        seed=seed,
        twin_seed=scenario.twin_seed,
        loc_reports=tuple(sorted(reports, key=lambda r: (r.event_time, r.msisdn))),
        outages=tuple(sorted(outages, key=lambda o: o.listed_at)),
        heartbeats=tuple(heartbeats),
        answer_key=answer_key,
        background=tuple(background),
        relocations=tuple(relocations),
    )


def _maybe_drop_out(
    noise: Noise, clock: TwinClock, rng: random.Random, minute: int, end: datetime
) -> tuple[str, int, datetime | None, Callable[[str], Dropout]] | None:
    """At most one dropout per minute, with chance dropouts_per_hour / 60. Returns the meter,
    the minute it comes back, when Telstra reports it (None if it is back before the network's
    timer runs out), and a function that builds the Dropout record once we know its msisdn."""
    if rng.random() >= noise.dropouts_per_hour / 60:
        return None
    online = [m.meter_id for m in clock.twin.meters if clock.state(m.meter_id).online]
    if not online:
        return None
    meter_id = rng.choice(online)
    lasts_min = rng.randint(*noise.back_after_min)
    dropped_at = clock.now + timedelta(seconds=rng.uniform(0, 60))
    timer = timedelta(seconds=rng.uniform(*noise.detection_delay_s))
    back_minute = minute + lasts_min
    back_at = clock.now + timedelta(minutes=lasts_min)
    # Telstra only reports it if the meter is still gone when the detection timer runs out.
    report = dropped_at + timer if back_at - dropped_at > timer else None
    clock.set_connected([meter_id], False)

    def record(msisdn: str) -> Dropout:
        return Dropout(
            meter_id, msisdn, dropped_at, back_at if back_at < end else None, report is not None
        )

    return meter_id, back_minute, report, record

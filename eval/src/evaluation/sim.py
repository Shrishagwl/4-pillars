"""Seeded runs for the evaluation, made by the digital twin (services/twin).

`simulate(kind, seed, settings)` builds a one-fault twin scenario, runs it with the twin's
`run_scenario`, and turns the result into a `Run`: the LoC events the engine sees, what the
Telstra APIs would say at any moment, and the answer key. Everything else in this package only
uses `Run`, so the systems and metrics don't need to know how the twin works inside.

What a run contains:
  - one main fault: a power cut, a Telstra network outage, a meter fault or a tamper
  - background dropouts from the twin's noise model: meters that lose signal and come back
    by themselves (nothing is wrong). Some last long enough for Telstra to send a code 7.
  - sometimes an older, unrelated network outage that is still listed for the same suburb.
    The twin doesn't model this, so it is added here. It is the case that fools a
    "check the Outage API" rule.

SimSettings holds the knobs the sensitivity tests turn. Defaults are the twin's own defaults
(see docs/twin-settings.md for where they come from).
"""

import random
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from engine.contracts import Cause, MeterSilentEvent, reason_group
from engine.topology import Meter, Topology
from twin.clock import DEFAULT_START
from twin.grid import build_twin
from twin.run import RunResult, run_scenario
from twin.scenario import Scenario, parse_scenario

KINDS: tuple[str, ...] = ("power", "network", "meter_fault", "tamper")
KIND_CAUSE: dict[str, Cause] = {
    "power": Cause.POWER,
    "network": Cause.NETWORK,
    "meter_fault": Cause.METER_FAULT,
    "tamper": Cause.TAMPER,
}
TWIN_KIND = {"power": "power", "network": "network", "meter_fault": "meter", "tamper": "tamper"}
TARGET = {"power": "transformer", "network": "suburb", "meter_fault": "meter", "tamper": "meter"}

FAULT_WINDOW_MIN = (5, 10)  # the fault starts somewhere in here, so runs differ in timing
HORIZON_MIN = 30  # how long we watch after the latest possible start


@dataclass(frozen=True)
class SimSettings:
    twin_seed: int = 42  # which map; the same for every run
    # Power cut: share of meters that manage to send a last gasp.
    last_gasp_rate: float = 0.7
    # Average seconds until the network notices a meter that just went quiet (no last gasp).
    # Runs pick between 2/3 and 4/3 of it, so the default is the twin's 120 to 240 s.
    detection_delay_s: float = 180.0
    # Average seconds until Telstra lists a network outage. Default: the twin's 10 to 30 min.
    outage_api_lag_s: float = 1200.0
    # Background dropouts across the whole fleet per hour (the twin allows up to 60).
    blips_per_hour: float = 4.0
    # Chance of an older listed outage in the same suburb that has nothing to do with the fault.
    stale_outage_rate: float = 0.25
    # Tamper: chance that Location Verification notices the SIM has moved once it is back.
    tamper_detect_rate: float = 0.9


@dataclass(frozen=True)
class Grid:
    topology: Topology
    meters: tuple[Meter, ...]
    by_transformer: dict[str, tuple[Meter, ...]]
    # The suburb most of a transformer's meters are in.
    transformer_suburb: dict[str, str]


@dataclass(frozen=True)
class Listing:
    """One outage entry in Network Availability."""

    suburb: str
    listed_at: datetime
    msisdns: frozenset[str]  # the SIMs really inside the outage area


@dataclass(frozen=True)
class Run:
    kind: str
    seed: int
    settings: SimSettings
    grid: Grid
    events: tuple[MeterSilentEvent, ...]  # sorted by eventTime
    event_times: tuple[datetime, ...]
    # Answer key
    truth: Cause
    truth_meter_ids: frozenset[str]
    fault_at: datetime
    # What the Telstra APIs would say
    listings: tuple[Listing, ...]
    moves: dict[str, datetime]  # msisdn -> when Location Verification starts saying FALSE
    restores: dict[str, datetime]  # msisdn -> when a dropout came back
    start: datetime
    end: datetime

    def events_until(self, when: datetime) -> tuple[MeterSilentEvent, ...]:
        return self.events[: bisect_right(self.event_times, when)]

    def outage_suburbs_at(self, when: datetime) -> set[str]:
        return {entry.suburb for entry in self.listings if entry.listed_at <= when}

    def outage_msisdns_at(self, when: datetime) -> set[str]:
        return {
            msisdn for entry in self.listings if entry.listed_at <= when for msisdn in entry.msisdns
        }

    def moved_msisdns_at(self, when: datetime) -> set[str]:
        return {msisdn for msisdn, moved_at in self.moves.items() if moved_at <= when}


@lru_cache(maxsize=8)
def build_grid(twin_seed: int) -> Grid:
    twin = build_twin(twin_seed)
    meters = tuple(Meter(m.meter_id, m.msisdn, m.transformer_id, m.suburb) for m in twin.meters)
    by_transformer: dict[str, list[Meter]] = {}
    for meter in meters:
        by_transformer.setdefault(meter.transformer_id, []).append(meter)
    transformer_suburb = {}
    for transformer_id, group in by_transformer.items():
        suburbs = [m.suburb for m in group]
        transformer_suburb[transformer_id] = max(sorted(set(suburbs)), key=suburbs.count)
    return Grid(
        Topology(meters),
        meters,
        {t: tuple(group) for t, group in by_transformer.items()},
        transformer_suburb,
    )


def scenario_for(kind: str, settings: SimSettings) -> Scenario:
    """The one-fault twin scenario for this kind, with the settings filled in."""
    mean = settings.detection_delay_s
    delay = [round(mean * 2 / 3), round(mean * 4 / 3)]
    fault: dict = {
        "kind": TWIN_KIND[kind],
        "at_min": list(FAULT_WINDOW_MIN),
        TARGET[kind]: "random",
        "detection_delay_s": delay,
    }
    if kind == "power":
        fault["last_gasp_share"] = settings.last_gasp_rate
    if kind == "network":
        lag_min = settings.outage_api_lag_s / 60
        fault["notice_lag_min"] = [round(lag_min / 2), round(lag_min * 3 / 2)]
    data: dict = {
        "name": f"eval-{kind}",
        "twin_seed": settings.twin_seed,
        "duration_min": FAULT_WINDOW_MIN[1] + HORIZON_MIN,
        "faults": [fault],
    }
    if settings.blips_per_hour > 0:
        data["noise"] = {"dropouts_per_hour": settings.blips_per_hour, "detection_delay_s": delay}
    return parse_scenario(data, source=data["name"])


def simulate(kind: str, seed: int, settings: SimSettings | None = None) -> Run:
    """One run. The same kind, seed and settings always give exactly the same run."""
    if kind not in KIND_CAUSE:
        raise ValueError(f"unknown kind {kind!r}, expected one of {KINDS}")
    settings = settings or SimSettings()
    scenario = scenario_for(kind, settings)
    result = run_scenario(scenario, seed)
    return _to_run(kind, seed, settings, scenario, result)


def _to_run(
    kind: str, seed: int, settings: SimSettings, scenario: Scenario, result: RunResult
) -> Run:
    grid = build_grid(settings.twin_seed)
    by_id = {m.meter_id: m for m in grid.meters}
    [incident] = result.answer_key
    start = DEFAULT_START
    end = start + timedelta(minutes=scenario.duration_min)
    # The twin's own generator is left alone; the extras below get their own.
    rng = random.Random(f"eval:{kind}:{seed}")

    truth_ids = frozenset(incident.meter_ids)
    listings = [
        Listing(
            notice.suburb,
            notice.listed_at,
            frozenset(by_id[mid].msisdn for mid in truth_ids),
        )
        for notice in result.outages
    ]

    # An older outage that is still listed for the suburb but covers other streets.
    if kind != "network" and truth_ids and rng.random() < settings.stale_outage_rate:
        fault_meters = [by_id[mid] for mid in sorted(truth_ids)]
        suburbs = [m.suburb for m in fault_meters]
        suburb = max(sorted(set(suburbs)), key=suburbs.count)
        fault_transformers = {m.transformer_id for m in fault_meters}
        others = sorted(
            t
            for t, s in grid.transformer_suburb.items()
            if s == suburb and t not in fault_transformers
        )
        if others:
            covered = [
                m.msisdn
                for transformer_id in rng.sample(others, min(2, len(others)))
                for m in grid.by_transformer[transformer_id]
            ]
            listings.append(Listing(suburb, start - timedelta(minutes=20), frozenset(covered)))

    moves = {
        r.msisdn: r.moved_at
        for r in result.relocations
        if rng.random() < settings.tamper_detect_rate
    }
    restores = {d.msisdn: d.back_at for d in result.background if d.back_at is not None}

    events = tuple(
        MeterSilentEvent(
            eventId=f"{kind}-{seed}-{i}",
            subscriptionId="twin",
            msisdn=report.msisdn,
            reasonCode=report.reason_code,
            reasonGroup=reason_group(report.reason_code),
            eventTime=report.event_time,
            receivedAt=report.event_time + timedelta(seconds=1),
        )
        for i, report in enumerate(result.loc_reports)
    )

    return Run(
        kind=kind,
        seed=seed,
        settings=settings,
        grid=grid,
        events=events,
        event_times=tuple(e.eventTime for e in events),
        truth=KIND_CAUSE[kind],
        truth_meter_ids=truth_ids,
        fault_at=incident.started_at,
        listings=tuple(sorted(listings, key=lambda entry: entry.listed_at)),
        moves=moves,
        restores=restores,
        start=start,
        end=end,
    )

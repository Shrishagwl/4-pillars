"""Fault-injection scenarios (#9): a YAML file says what breaks, where and when.

    name: power-outage
    duration_min: 240
    faults:
      - kind: power
        at_min: 120
        transformer: random
        restore_after_min: 90

Checking happens in two stages, because a file can be wrong in two different ways:
  1. `load_scenario`: is the file itself well formed? (right fields, right types, sensible
     numbers). Pydantic does this from the model classes below.
  2. `schedule`: does it make sense for this twin? (does transformer T-07 exist?). The file
     alone can't answer that, so it is checked against a built twin.
Both raise ScenarioError with a message that names the problem, so a typo in a scenario file
fails loudly at load time instead of silently running the wrong experiment.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import ErrorDetails

from .grid import Twin

RANDOM = "random"  # any fault target can say "random"; the run's seed then picks one


class Cause(StrEnum):
    """The true cause of a fault. Same values as the engine's Cause (engine/contracts.py), so the
    answer key and the engine's verdicts can be compared directly."""

    POWER = "POWER"
    NETWORK = "NETWORK"
    METER_FAULT = "METER_FAULT"
    TAMPER = "TAMPER"


class ScenarioError(ValueError):
    pass


class _Strict(BaseModel):
    # extra="forbid": an unknown field is an error, so "restore_afer_min" (typo) is caught
    # instead of being quietly ignored. frozen=True: a loaded scenario can't be changed.
    model_config = ConfigDict(extra="forbid", frozen=True)


def _low_then_high(pair: tuple[float, float]) -> tuple[float, float]:
    low, high = pair
    if not 0 <= low <= high:
        raise ValueError(f"needs [low, high] with 0 <= low <= high, got [{low}, {high}]")
    return pair


def _at_most_one(pair: tuple[float, float]) -> tuple[float, float]:
    if pair[1] > 1:
        raise ValueError(f"a share can't be above 1, got {pair[1]}")
    return pair


# A [low, high] pair in the file; each run picks a value in between with its seed.
SecondsRange = Annotated[tuple[float, float], AfterValidator(_low_then_high)]
MinutesRange = Annotated[tuple[int, int], AfterValidator(_low_then_high)]
ShareRange = Annotated[
    tuple[float, float], AfterValidator(_low_then_high), AfterValidator(_at_most_one)
]


# A time in the file is either a fixed minute (120) or a window ([100, 140]). With a window,
# each run picks a minute inside it with its seed, so runs differ in timing as well as in
# target (#32). A fixed minute uses no randomness at all.
MinuteOrWindow = Annotated[int, Field(ge=0)] | MinutesRange


def _pick(value: MinuteOrWindow, rng: random.Random) -> int:
    return value if isinstance(value, int) else rng.randint(*value)


def _latest(value: MinuteOrWindow) -> int:
    return value if isinstance(value, int) else value[1]


class _FaultBase(_Strict):
    at_min: MinuteOrWindow = Field(description="minutes after the run starts")
    restore_after_min: MinuteOrWindow | None = Field(
        default=None, description="minutes until it's fixed; leave out for 'never'"
    )

    @field_validator("restore_after_min")
    @classmethod
    def _repair_takes_time(cls, value: MinuteOrWindow | None) -> MinuteOrWindow | None:
        if value is not None and (value if isinstance(value, int) else value[0]) <= 0:
            raise ValueError("a repair takes at least 1 minute")
        return value


class PowerFault(_FaultBase):
    """A transformer fails (#18). All its meters lose power within a few seconds."""

    kind: Literal["power"]
    transformer: str  # e.g. "T-07", or "random"
    drop_within_s: float = Field(default=10, ge=0)  # every meter is off within this time
    last_gasp_share: float = Field(default=0.7, ge=0, le=1)  # share that send code 6
    detection_delay_s: SecondsRange = (120, 240)  # the rest: code 7 this much later

    cause: ClassVar[Cause] = Cause.POWER


class NetworkFault(_FaultBase):
    """Telstra's network fails in a suburb (#21). Meters keep their power but lose signal, so
    none can send a last gasp: they just go quiet and time out (code 7)."""

    kind: Literal["network"]
    suburb: str  # e.g. "Coburg", or "random"
    drop_share: ShareRange = (0.6, 0.9)  # this share of the suburb's meters lose signal
    drop_over_s: float = Field(default=180, ge=0)  # one after another, over this long
    detection_delay_s: SecondsRange = (120, 240)  # the network notices this much later
    notice_lag_min: MinutesRange = (10, 30)  # Telstra lists the outage this long after it starts

    cause: ClassVar[Cause] = Cause.NETWORK


class MeterFault(_FaultBase):
    """One meter breaks on its own (#28), for example a dead modem. It dies without warning, so
    there is no last gasp: the network notices when its detection timer runs out (code 7).
    restore_after_min is when a technician has replaced it."""

    kind: Literal["meter"]
    meter: str  # e.g. "M-0412", or "random"
    detection_delay_s: SecondsRange = (120, 240)

    cause: ClassVar[Cause] = Cause.METER_FAULT


class TamperFault(_FaultBase):
    """A meter is tampered with and moved (#31)."""

    kind: Literal["tamper"]
    meter: str

    cause: ClassVar[Cause] = Cause.TAMPER


class Noise(_Strict):
    """Background dropouts on a normal day (#28). Now and then a meter loses signal for a few
    minutes and comes back by itself. These are not incidents: nobody needs to go anywhere. If a
    dropout outlasts the network's detection timer, Telstra still sends a code 7 for it, which
    is exactly what can fool an engine into a needless dispatch."""

    dropouts_per_hour: float = Field(default=2.0, ge=0, le=60)
    back_after_min: MinutesRange = (1, 15)
    detection_delay_s: SecondsRange = (120, 240)

    @field_validator("back_after_min")
    @classmethod
    def _at_least_a_minute(cls, value: tuple[int, int]) -> tuple[int, int]:
        if value[0] < 1:
            raise ValueError("a dropout lasts at least 1 minute")
        return value


# The `kind` field decides which of the four shapes a fault must have. Pydantic calls this a
# discriminated union: it reads `kind` first, then checks the rest against the matching class.
Fault = Annotated[PowerFault | NetworkFault | MeterFault | TamperFault, Field(discriminator="kind")]


class Scenario(_Strict):
    name: str
    description: str = ""
    twin_seed: int = 42  # which twin to build; the same map for every run of this scenario
    duration_min: int = Field(gt=0)
    faults: list[Fault] = []
    noise: Noise | None = None  # background dropouts; leave out for a perfectly clean network

    @model_validator(mode="after")
    def _faults_start_inside_the_run(self) -> Scenario:
        for i, fault in enumerate(self.faults):
            if _latest(fault.at_min) >= self.duration_min:
                raise ValueError(
                    f"faults[{i}] can start at minute {_latest(fault.at_min)}, "
                    f"but the run only lasts {self.duration_min} minutes"
                )
        return self


def load_scenario(path: Path | str) -> Scenario:
    """Read and check one scenario file."""
    path = Path(path)
    try:
        # safe_load, never load: plain yaml.load can build arbitrary Python objects from a
        # file, so a malicious file could run code. safe_load only builds plain data.
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ScenarioError(f"{path.name}: not valid YAML: {e}") from e
    return parse_scenario(data, source=path.name)


def parse_scenario(data: object, source: str = "scenario") -> Scenario:
    """Check already-loaded data (a dict) against the Scenario model."""
    try:
        return Scenario.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(_describe(err) for err in e.errors())
        raise ScenarioError(f"{source}: {problems}") from e


def _describe(err: ErrorDetails) -> str:
    """One problem as "where: what". A check on the whole scenario (like "a fault must start
    before the run ends") has no single field, so it gets no "where"."""
    where = ".".join(str(part) for part in err["loc"])
    what = err["msg"].removeprefix("Value error, ")
    return f"{where}: {what}" if where else what


@dataclass(frozen=True, slots=True)
class ScheduledFault:
    """One fault, pinned down for one run: its target is a real id, its meters are known, and
    its start and repair are exact minutes."""

    fault: PowerFault | NetworkFault | MeterFault | TamperFault
    target: str  # the transformer, suburb or meter id it hits
    meter_ids: tuple[str, ...]  # every meter in the target
    at_min: int
    restore_at_min: int | None  # None: never repaired


def schedule(scenario: Scenario, twin: Twin, rng: random.Random) -> list[ScheduledFault]:
    """Resolve every fault's target against the twin and return them in time order.

    "random" targets and [low, high] time windows are picked with `rng`, so the same seed picks
    the same targets and times.
    """
    choices = {
        "transformer": sorted(t.id for t in twin.transformers),
        "suburb": sorted(s.name for s in twin.suburbs),
        "meter": sorted(m.meter_id for m in twin.meters),
    }
    members = {
        "transformer": lambda tid: twin.meters_on(tid),
        "suburb": lambda name: twin.meters_in(name),
        "meter": lambda mid: [m for m in twin.meters if m.meter_id == mid],
    }

    planned = []
    for i, fault in enumerate(scenario.faults):
        field = _target_field(fault)
        wanted = getattr(fault, field)
        if wanted == RANDOM:
            target = rng.choice(choices[field])
        elif wanted in choices[field]:
            target = wanted
        else:
            raise ScenarioError(
                f"{scenario.name}: faults[{i}] {field} {wanted!r} is not in twin "
                f"{scenario.twin_seed} (try one of {choices[field][:3]}... or {RANDOM!r})"
            )
        meter_ids = tuple(m.meter_id for m in members[field](target))
        at = _pick(fault.at_min, rng)
        restore = (
            None if fault.restore_after_min is None else at + _pick(fault.restore_after_min, rng)
        )
        planned.append(ScheduledFault(fault, target, meter_ids, at, restore))

    # sorted() is stable: two faults at the same minute keep the order they have in the file.
    return sorted(planned, key=lambda p: p.at_min)


def _target_field(fault: PowerFault | NetworkFault | MeterFault | TamperFault) -> str:
    if isinstance(fault, PowerFault):
        return "transformer"
    if isinstance(fault, NetworkFault):
        return "suburb"
    return "meter"

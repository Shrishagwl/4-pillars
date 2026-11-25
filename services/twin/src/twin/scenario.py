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
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
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


class _FaultBase(_Strict):
    at_min: int = Field(ge=0, description="minutes after the run starts")
    restore_after_min: int | None = Field(
        default=None, gt=0, description="minutes until it's fixed; leave out for 'never'"
    )


class PowerFault(_FaultBase):
    """A transformer fails (#18). All its meters lose power within a few seconds."""

    kind: Literal["power"]
    transformer: str  # e.g. "T-07", or "random"
    drop_within_s: float = Field(default=10, ge=0)  # every meter is off within this time
    last_gasp_share: float = Field(default=0.7, ge=0, le=1)  # share that send code 6
    detection_delay_s: tuple[float, float] = (120, 240)  # the rest: code 7 this much later

    cause: ClassVar[Cause] = Cause.POWER


class NetworkFault(_FaultBase):
    """Telstra's network fails in a suburb (#21)."""

    kind: Literal["network"]
    suburb: str  # e.g. "Coburg", or "random"

    cause: ClassVar[Cause] = Cause.NETWORK


class MeterFault(_FaultBase):
    """One meter breaks (#28)."""

    kind: Literal["meter"]
    meter: str  # e.g. "M-0412", or "random"

    cause: ClassVar[Cause] = Cause.METER_FAULT


class TamperFault(_FaultBase):
    """A meter is tampered with and moved (#31)."""

    kind: Literal["tamper"]
    meter: str

    cause: ClassVar[Cause] = Cause.TAMPER


# The `kind` field decides which of the four shapes a fault must have. Pydantic calls this a
# discriminated union: it reads `kind` first, then checks the rest against the matching class.
Fault = Annotated[PowerFault | NetworkFault | MeterFault | TamperFault, Field(discriminator="kind")]


class Scenario(_Strict):
    name: str
    description: str = ""
    twin_seed: int = 42  # which twin to build; the same map for every run of this scenario
    duration_min: int = Field(gt=0)
    faults: list[Fault] = []

    @model_validator(mode="after")
    def _faults_start_inside_the_run(self) -> Scenario:
        for i, fault in enumerate(self.faults):
            if fault.at_min >= self.duration_min:
                raise ValueError(
                    f"faults[{i}] starts at minute {fault.at_min}, "
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
    """One fault, pinned down for one run: its target is a real id and its meters are known."""

    fault: PowerFault | NetworkFault | MeterFault | TamperFault
    target: str  # the transformer, suburb or meter id it hits
    meter_ids: tuple[str, ...]  # every meter in the target

    @property
    def at_min(self) -> int:
        return self.fault.at_min

    @property
    def restore_at_min(self) -> int | None:
        if self.fault.restore_after_min is None:
            return None
        return self.fault.at_min + self.fault.restore_after_min


def schedule(scenario: Scenario, twin: Twin, rng: random.Random) -> list[ScheduledFault]:
    """Resolve every fault's target against the twin and return them in time order.

    "random" targets are picked with `rng`, so the same seed picks the same targets.
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
        planned.append(ScheduledFault(fault, target, meter_ids))

    # sorted() is stable: two faults at the same minute keep the order they have in the file.
    return sorted(planned, key=lambda p: p.at_min)


def _target_field(fault: PowerFault | NetworkFault | MeterFault | TamperFault) -> str:
    if isinstance(fault, PowerFault):
        return "transformer"
    if isinstance(fault, NetworkFault):
        return "suburb"
    return "meter"

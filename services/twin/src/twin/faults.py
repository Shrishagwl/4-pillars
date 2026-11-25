"""Fault models: what each kind of fault does to the meters and which LoC reports it causes.

Each model gets the scheduled fault, the live clock and the run's random generator. It flips the
meters' switches on the clock and returns the Loss of Connectivity reports Telstra would send.

Power outage (#18), the fingerprint the engine looks for:
  - every meter on the transformer goes off within a few seconds of each other;
  - most send a "last gasp" as they die (LoC code 6, detached): the meter's capacitor holds just
    enough charge to tell the network it's going;
  - the rest just vanish, and the network only notices when its detection timer runs out a few
    minutes later (LoC code 7, maximum detection time expired).
Default numbers match the engine's own test fixtures (engine/tests/test_pipeline.py); #23
calibrates them against the research in #3.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clock import TwinClock
from .scenario import PowerFault, ScheduledFault

LOC_LAST_GASP = 6  # detached / deregistered
LOC_DETECTION_TIMEOUT = 7  # maximum detection time expired


@dataclass(frozen=True, slots=True)
class LocReport:
    """One Loss of Connectivity report, as Telstra would send it to our callback."""

    msisdn: str
    reason_code: int
    event_time: datetime  # when the device lost connectivity

    def to_telstra(self) -> dict[str, object]:
        """The exact JSON shape of Telstra's monitoringEventReports entry
        (packages/contracts/src/loss-of-connectivity.ts)."""
        return {
            "monitoringType": "LOSS_OF_CONNECTIVITY",
            "msisdn": self.msisdn,
            "lossOfConnectReason": self.reason_code,
            "eventTime": self.event_time.isoformat().replace("+00:00", "Z"),
        }


def power_outage(planned: ScheduledFault, clock: TwinClock, rng: random.Random) -> list[LocReport]:
    fault = planned.fault
    assert isinstance(fault, PowerFault)
    start = clock.now
    msisdn = {m.meter_id: m.msisdn for m in clock.twin.meters}
    low, high = fault.detection_delay_s

    reports = []
    for meter_id in planned.meter_ids:
        # A meter that is already offline (broken, or already cut) has nothing left to lose,
        # so it sends no new report. Checked before switching anything off.
        if not clock.state(meter_id).online:
            continue
        dropped_at = start + timedelta(seconds=rng.uniform(0, fault.drop_within_s))
        if rng.random() < fault.last_gasp_share:
            reports.append(LocReport(msisdn[meter_id], LOC_LAST_GASP, dropped_at))
        else:
            noticed_at = dropped_at + timedelta(seconds=rng.uniform(low, high))
            reports.append(LocReport(msisdn[meter_id], LOC_DETECTION_TIMEOUT, noticed_at))

    clock.set_powered(planned.meter_ids, False)
    return reports


def restore_power(planned: ScheduledFault, clock: TwinClock) -> None:
    clock.set_powered(planned.meter_ids, True)

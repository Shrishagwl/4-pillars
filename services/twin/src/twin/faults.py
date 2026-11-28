"""Fault models: what each kind of fault does to the meters and which LoC reports it causes.

Each model gets the scheduled fault, the live clock and the run's random generator. It flips the
meters' switches on the clock and returns the Loss of Connectivity reports Telstra would send.

Power outage (#18), the fingerprint the engine looks for:
  - every meter on the transformer goes off within a few seconds of each other;
  - most send a "last gasp" as they die (a "detached" LoC code): the meter's capacitor holds just
    enough charge to tell the network it's going;
  - the rest just vanish, and the network only notices when its detection timer runs out a few
    minutes later (a "maximum detection time expired" code).
Network outage (#21), a different fingerprint:
  - only part of a suburb goes quiet (60-90%), one meter after another over a few minutes,
    across many transformers;
  - no last gasps, because the meters still have power: every report is a detection timeout;
  - some time later, Telstra lists the outage on its Network Availability API.
Meter failure (#28): one meter dies without warning (no last gasp), a timeout when the network's
timer runs out, and nothing else around it goes quiet.
Tamper (#31): one meter is unplugged (often a last gasp, like a tiny power cut), then its SIM
comes back online kilometres away, which Location Verification can catch.
Where the numbers come from, and which are estimates: docs/twin-calibration.md (#23).
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from .clock import TwinClock
from .grid import M_PER_DEG_LAT, M_PER_DEG_LON
from .scenario import MeterFault, NetworkFault, PowerFault, ScheduledFault, TamperFault

# Telstra's LoC codes come in families by core network (Getting Started page on dev.telstra.com):
# MME is 4G, SGSN is 2G/3G, AMF is 5G. Telstra switched 3G off on 28 Oct 2024, so no SGSN codes.
# Meter SIMs are mostly 4G (LTE / Cat-M1); we put about 1 in 10 on 5G (an estimate, see #23).
LOC_LAST_GASP_4G = 0  # UE_DETACHED_MME
LOC_TIMEOUT_4G = 2  # MAX_DETECTION_TIME_EXPIRED_MME
LOC_LAST_GASP_5G = 6  # DEREGISTERED (AMF)
LOC_TIMEOUT_5G = 7  # MAX_DETECTION_TIME_EXPIRED (AMF)
LAST_GASP_CODES = frozenset({LOC_LAST_GASP_4G, LOC_LAST_GASP_5G})
TIMEOUT_CODES = frozenset({LOC_TIMEOUT_4G, LOC_TIMEOUT_5G})
FIVE_G_SHARE = 0.10


def on_5g(msisdn: str) -> bool:
    """Which core a SIM is on. Fixed per SIM (a hash), so it doesn't change between runs."""
    return zlib.crc32(msisdn.encode()) % 100 < FIVE_G_SHARE * 100


def last_gasp_code(msisdn: str) -> int:
    return LOC_LAST_GASP_5G if on_5g(msisdn) else LOC_LAST_GASP_4G


def timeout_code(msisdn: str) -> int:
    return LOC_TIMEOUT_5G if on_5g(msisdn) else LOC_TIMEOUT_4G


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
            reports.append(
                LocReport(msisdn[meter_id], last_gasp_code(msisdn[meter_id]), dropped_at)
            )
        else:
            noticed_at = dropped_at + timedelta(seconds=rng.uniform(low, high))
            reports.append(LocReport(msisdn[meter_id], timeout_code(msisdn[meter_id]), noticed_at))

    clock.set_powered(planned.meter_ids, False)
    return reports


def restore_power(planned: ScheduledFault, clock: TwinClock) -> None:
    clock.set_powered(planned.meter_ids, True)


@dataclass(frozen=True, slots=True)
class OutageNotice:
    """One outage as Telstra's Network Availability API would list it (#21).

    Times are UTC here. Telstra's real API uses its own format ("2026-05-13 00:03:00
    Australia/Melbourne"); converting is telstra-fake's and telstra-gateway's job.
    """

    suburb: str
    postcode: str
    started_at: datetime
    listed_at: datetime  # when it first shows up in the API; before this the engine can't see it
    restored_at: datetime | None


def network_outage(
    planned: ScheduledFault, clock: TwinClock, rng: random.Random
) -> list[LocReport]:
    fault = planned.fault
    assert isinstance(fault, NetworkFault)
    start = clock.now
    msisdn = {m.meter_id: m.msisdn for m in clock.twin.meters}
    low, high = fault.detection_delay_s

    online = [mid for mid in planned.meter_ids if clock.state(mid).online]
    share = rng.uniform(*fault.drop_share)
    # sample() picks without repeats, and sorting keeps the report order tidy and repeatable.
    hit = sorted(rng.sample(online, round(share * len(online))))

    reports = []
    for meter_id in hit:
        lost_signal_at = start + timedelta(seconds=rng.uniform(0, fault.drop_over_s))
        noticed_at = lost_signal_at + timedelta(seconds=rng.uniform(low, high))
        reports.append(LocReport(msisdn[meter_id], timeout_code(msisdn[meter_id]), noticed_at))

    clock.set_connected(hit, False)
    return reports


def restore_network(planned: ScheduledFault, clock: TwinClock) -> None:
    clock.set_connected(planned.meter_ids, True)


def meter_failure(planned: ScheduledFault, clock: TwinClock, rng: random.Random) -> list[LocReport]:
    fault = planned.fault
    assert isinstance(fault, MeterFault)
    [meter_id] = planned.meter_ids
    if not clock.state(meter_id).online:
        return []
    died_at = clock.now + timedelta(seconds=rng.uniform(0, 60))
    noticed_at = died_at + timedelta(seconds=rng.uniform(*fault.detection_delay_s))
    clock.set_healthy([meter_id], False)
    return [LocReport(_msisdn(clock, meter_id), timeout_code(_msisdn(clock, meter_id)), noticed_at)]


def restore_meter(planned: ScheduledFault, clock: TwinClock) -> None:
    clock.set_healthy(planned.meter_ids, True)


@dataclass(frozen=True, slots=True)
class Relocation:
    """Where a tampered meter's SIM really is from `moved_at` on (#31). This is what Telstra's
    Location Verification would see: ask about the meter's own address and it answers FALSE."""

    meter_id: str
    msisdn: str
    lat: float
    lon: float
    moved_at: datetime
    distance_m: float  # from the meter's registered address


def tamper_removal(
    planned: ScheduledFault, clock: TwinClock, rng: random.Random
) -> list[LocReport]:
    fault = planned.fault
    assert isinstance(fault, TamperFault)
    [meter_id] = planned.meter_ids
    if not clock.state(meter_id).online:
        return []
    msisdn = _msisdn(clock, meter_id)
    unplugged_at = clock.now + timedelta(seconds=rng.uniform(0, 60))
    clock.set_powered([meter_id], False)
    if rng.random() < fault.last_gasp_share:
        return [LocReport(msisdn, last_gasp_code(msisdn), unplugged_at)]
    noticed_at = unplugged_at + timedelta(seconds=rng.uniform(*fault.detection_delay_s))
    return [LocReport(msisdn, timeout_code(msisdn), noticed_at)]


def tamper_reappear(planned: ScheduledFault, clock: TwinClock, rng: random.Random) -> Relocation:
    """The SIM comes back online somewhere else: heartbeats resume, from the wrong place."""
    fault = planned.fault
    assert isinstance(fault, TamperFault)
    [meter_id] = planned.meter_ids
    home = next(m for m in clock.twin.meters if m.meter_id == meter_id)
    distance = rng.uniform(*fault.moved_m)
    bearing = rng.uniform(0, 2 * math.pi)  # any direction
    lat = home.lat + distance * math.cos(bearing) / M_PER_DEG_LAT
    lon = home.lon + distance * math.sin(bearing) / M_PER_DEG_LON
    clock.set_powered([meter_id], True)
    return Relocation(meter_id, home.msisdn, lat, lon, clock.now, distance)


def _msisdn(clock: TwinClock, meter_id: str) -> str:
    return next(m.msisdn for m in clock.twin.meters if m.meter_id == meter_id)

"""Twin clock and live meter state (#12).

The twin's time is simulated: it only moves when `step()` is called, one minute at a time, so a
day of meter traffic can be replayed in well under a second and every run is repeatable. Never
read the real clock (`datetime.now()`) in here: two runs started a second apart would differ.

Each meter has three switches. It is online, and sends a heartbeat every 15 minutes, only while
all three are on:
  - powered:   its transformer has power   (cut by a power outage, #18)
  - connected: the mobile network reaches it (cut by a network outage, #21)
  - healthy:   the meter itself works      (broken by a meter failure, #28)
The fault models flip these switches; the clock just reports what follows from them.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from .grid import Meter, Twin

HEARTBEAT_EVERY_MIN = 15
# A fixed start, so a run's timestamps are the same every time. Any date works.
DEFAULT_START = datetime(2026, 11, 25, 0, 0, tzinfo=UTC)


@dataclass(slots=True)
class MeterState:
    powered: bool = True
    connected: bool = True
    healthy: bool = True
    last_heartbeat: datetime | None = None

    @property
    def online(self) -> bool:
        return self.powered and self.connected and self.healthy


@dataclass(frozen=True, slots=True)
class Heartbeat:
    meter_id: str
    msisdn: str
    time: datetime


class TwinClock:
    """Moves the twin forward minute by minute and holds every meter's live state."""

    def __init__(self, twin: Twin, start: datetime = DEFAULT_START) -> None:
        self.twin = twin
        self.now = start
        self.minute = 0  # minutes since start
        self._meters = {m.meter_id: m for m in twin.meters}
        self._state = {m.meter_id: MeterState() for m in twin.meters}

        # Real meters don't all report on the same minute, or the network would see a burst of
        # 2,000 messages every quarter hour. Each meter gets its own slot (0 to 14) within the
        # 15-minute cycle. The generator is seeded from the twin's seed, plus a label so its
        # numbers don't repeat the ones build_twin drew from the same seed.
        rng = random.Random(f"heartbeat-slots:{twin.seed}")
        self._by_slot: list[list[Meter]] = [[] for _ in range(HEARTBEAT_EVERY_MIN)]
        for m in twin.meters:
            self._by_slot[rng.randrange(HEARTBEAT_EVERY_MIN)].append(m)

    # --- moving time ----------------------------------------------------------------------------

    def step(self) -> list[Heartbeat]:
        """Advance one minute and return the heartbeats sent in that minute."""
        self.now += timedelta(minutes=1)
        self.minute += 1
        beats = []
        for m in self._by_slot[self.minute % HEARTBEAT_EVERY_MIN]:
            state = self._state[m.meter_id]
            if state.online:
                state.last_heartbeat = self.now
                beats.append(Heartbeat(m.meter_id, m.msisdn, self.now))
        return beats

    def run(self, minutes: int) -> Iterator[Heartbeat]:
        """Advance `minutes` minutes, yielding heartbeats as they happen.

        A generator: the caller can stream events onward (to a file, an API, a test) one at a
        time, without holding a whole day of heartbeats in memory.
        """
        for _ in range(minutes):
            yield from self.step()

    # --- reading state (queries) -----------------------------------------------------------------

    def state(self, meter_id: str) -> MeterState:
        """A copy of one meter's state. Changing the copy doesn't change the twin; only the
        set_* methods below do, so every change to the twin goes through one place."""
        return replace(self._state[meter_id])

    def online_count(self) -> int:
        return sum(s.online for s in self._state.values())

    # --- changing state (commands, used by the fault models) --------------------------------------

    def set_powered(self, meter_ids: Iterable[str], on: bool) -> None:
        for mid in meter_ids:
            self._state[mid].powered = on

    def set_connected(self, meter_ids: Iterable[str], on: bool) -> None:
        for mid in meter_ids:
            self._state[mid].connected = on

    def set_healthy(self, meter_ids: Iterable[str], on: bool) -> None:
        for mid in meter_ids:
            self._state[mid].healthy = on

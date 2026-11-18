"""Which meter sits where: the engine's view of the grid.

The twin owns the real layout. The engine only needs to look a meter up by its SIM number
(msisdn) and find out which transformer feeds it and which suburb it is in.
"""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Meter:
    meter_id: str
    msisdn: str
    transformer_id: str
    suburb: str


class Topology:
    """Lookup table from msisdn to Meter."""

    def __init__(self, meters: Iterable[Meter]) -> None:
        self._by_msisdn: dict[str, Meter] = {}
        for meter in meters:
            if meter.msisdn in self._by_msisdn:
                raise ValueError(f"duplicate msisdn in topology: {meter.msisdn}")
            self._by_msisdn[meter.msisdn] = meter

    def __len__(self) -> int:
        return len(self._by_msisdn)

    def get(self, msisdn: str) -> Meter | None:
        return self._by_msisdn.get(msisdn)

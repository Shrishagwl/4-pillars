"""Which meter sits where: the engine's view of the grid.

The twin owns the real layout. The engine only needs to look a meter up by its SIM number
(msisdn) and find out which transformer feeds it and which suburb it is in.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Meter:
    meter_id: str
    msisdn: str
    transformer_id: str
    suburb: str


class Topology:
    """Lookup table from msisdn to Meter, plus how many meters each transformer and suburb has."""

    def __init__(self, meters: Iterable[Meter]) -> None:
        self._by_msisdn: dict[str, Meter] = {}
        self._per_transformer: Counter[str] = Counter()
        self._per_suburb: Counter[str] = Counter()
        for meter in meters:
            if meter.msisdn in self._by_msisdn:
                raise ValueError(f"duplicate msisdn in topology: {meter.msisdn}")
            self._by_msisdn[meter.msisdn] = meter
            self._per_transformer[meter.transformer_id] += 1
            self._per_suburb[meter.suburb] += 1

    def __len__(self) -> int:
        return len(self._by_msisdn)

    def get(self, msisdn: str) -> Meter | None:
        return self._by_msisdn.get(msisdn)

    def meters_on_transformer(self, transformer_id: str) -> int:
        return self._per_transformer[transformer_id]

    def meters_in_suburb(self, suburb: str) -> int:
        return self._per_suburb[suburb]

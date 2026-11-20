"""Grid version of the digital twin (#6): suburbs, transformers and meters, built from one seed.

Every meter belongs to two groupings that overlap but don't match:
  - a transformer (power): if it fails, all its meters go silent together;
  - a suburb (network): Telstra reports outages by suburb, so a network fault silences a suburb.
Transformer areas near a suburb border spill into the next suburb. That mismatch is what lets the
engine tell a power outage from a network outage.

In #26 the rectangles below are replaced by real ABS suburb shapes. Only `Suburb.contains` changes;
everything else asks "which suburb is this point in?" through `suburb_of`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

# A box around Coburg, Melbourne (degrees). South is the more negative latitude.
NORTH, SOUTH = -37.735, -37.775
WEST, EAST = 144.940, 144.990

# 2 x 2 grid of stand-in suburbs: rows from north to south, columns from west to east.
SUBURB_GRID: list[list[tuple[str, str]]] = [
    [("Pascoe Vale South", "3044"), ("Coburg", "3058")],
    [("Brunswick West", "3055"), ("Brunswick", "3056")],
]

N_TRANSFORMERS = 20
METERS_PER_TRANSFORMER = (50, 150)  # inclusive range, drawn per transformer
METER_SPREAD_M = 300  # standard deviation of the meter scatter around its transformer
TRANSFORMER_EDGE_MARGIN_M = 400  # keep transformers this far inside the box
TRANSFORMER_MIN_GAP_M = 600  # no two transformers closer than this
MSISDN_PREFIX = "614"  # Australian mobiles: 61 4xx xxx xxx, 11 digits in total

# One degree of latitude is about 111 km everywhere. One degree of longitude shrinks towards the
# poles by cos(latitude): about 88 km here. Converting metres to degrees separately for each axis
# keeps the meter clusters round instead of squashed.
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians((NORTH + SOUTH) / 2))


@dataclass(frozen=True, slots=True)
class Suburb:
    name: str
    postcode: str
    south: float
    north: float
    west: float
    east: float

    def contains(self, lat: float, lon: float) -> bool:
        # Half-open intervals: a point exactly on a shared border belongs to one suburb only.
        return self.south <= lat < self.north and self.west <= lon < self.east


@dataclass(frozen=True, slots=True)
class Transformer:
    id: str  # e.g. "T-07"
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Meter:
    # The first four fields match the engine's Meter (services/engine/src/engine/topology.py),
    # so the engine can build its Topology straight from the twin's meters.
    meter_id: str  # e.g. "M-0412"
    msisdn: str  # the SIM's phone number, e.g. "61412345678"
    transformer_id: str
    suburb: str
    postcode: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Twin:
    """Everything the twin knows about the layout. Frozen, so a built twin never changes, and two
    twins built from the same seed compare equal with ==."""

    seed: int
    suburbs: tuple[Suburb, ...]
    transformers: tuple[Transformer, ...]
    meters: tuple[Meter, ...]

    def meters_on(self, transformer_id: str) -> list[Meter]:
        return [m for m in self.meters if m.transformer_id == transformer_id]

    def meters_in(self, suburb: str) -> list[Meter]:
        return [m for m in self.meters if m.suburb == suburb]


def _edges(start: float, end: float, parts: int) -> list[float]:
    """Border positions computed once, so neighbours share the exact same float (no gaps or
    overlaps from rounding), with the outer edges pinned exactly to the box."""
    step = (end - start) / parts
    return [start] + [start + i * step for i in range(1, parts)] + [end]


def make_suburbs() -> list[Suburb]:
    """Split the box into the SUBURB_GRID rectangles."""
    lat_edges = _edges(NORTH, SOUTH, len(SUBURB_GRID))  # north to south
    lon_edges = _edges(WEST, EAST, len(SUBURB_GRID[0]))  # west to east
    suburbs = []
    for r, row in enumerate(SUBURB_GRID):
        for c, (name, postcode) in enumerate(row):
            suburbs.append(
                Suburb(
                    name,
                    postcode,
                    south=lat_edges[r + 1],
                    north=lat_edges[r],
                    west=lon_edges[c],
                    east=lon_edges[c + 1],
                )
            )
    return suburbs


def suburb_of(lat: float, lon: float, suburbs: list[Suburb]) -> Suburb | None:
    """The suburb containing this point, or None if it falls outside every suburb."""
    return next((s for s in suburbs if s.contains(lat, lon)), None)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in metres. A flat approximation, fine over a few kilometres."""
    return math.hypot((lat1 - lat2) * M_PER_DEG_LAT, (lon1 - lon2) * M_PER_DEG_LON)


def _place_transformers(rng: random.Random) -> list[Transformer]:
    """Uniformly inside the box (minus a margin), redrawing any spot too close to one already
    placed. Redrawing until a condition holds is called rejection sampling."""
    margin_lat = TRANSFORMER_EDGE_MARGIN_M / M_PER_DEG_LAT
    margin_lon = TRANSFORMER_EDGE_MARGIN_M / M_PER_DEG_LON
    placed: list[Transformer] = []
    attempts = 0
    while len(placed) < N_TRANSFORMERS:
        attempts += 1
        if attempts > 10_000:
            raise RuntimeError("could not space the transformers out; lower TRANSFORMER_MIN_GAP_M")
        lat = rng.uniform(SOUTH + margin_lat, NORTH - margin_lat)
        lon = rng.uniform(WEST + margin_lon, EAST - margin_lon)
        if all(distance_m(lat, lon, t.lat, t.lon) >= TRANSFORMER_MIN_GAP_M for t in placed):
            placed.append(Transformer(f"T-{len(placed) + 1:02d}", lat, lon))
    return placed


def _scatter_point(
    rng: random.Random, t: Transformer, suburbs: list[Suburb]
) -> tuple[float, float, Suburb]:
    """A point near transformer t (normal scatter), redrawn if it lands outside every suburb.
    Without the redraw, a transformer near the box edge would lose meters off the map."""
    while True:
        lat = rng.gauss(t.lat, METER_SPREAD_M / M_PER_DEG_LAT)
        lon = rng.gauss(t.lon, METER_SPREAD_M / M_PER_DEG_LON)
        suburb = suburb_of(lat, lon, suburbs)
        if suburb is not None:
            return lat, lon, suburb


def build_twin(seed: int) -> Twin:
    """The whole layout from one seed. Same seed, same twin, every time.

    All randomness comes from this one seeded generator, used in a fixed order. Never call the
    global `random.*` functions in the twin: they are shared by every library in the process, so
    one stray call elsewhere would silently change the twin.
    """
    rng = random.Random(seed)
    suburbs = make_suburbs()
    transformers = _place_transformers(rng)
    counts = [rng.randint(*METERS_PER_TRANSFORMER) for _ in transformers]

    # Unique phone numbers: sample without replacement, so no two meters share an msisdn
    # (the engine's Topology refuses duplicates).
    numbers = rng.sample(range(10**8), sum(counts))

    meters: list[Meter] = []
    for t, count in zip(transformers, counts, strict=True):
        for _ in range(count):
            lat, lon, suburb = _scatter_point(rng, t, suburbs)
            n = len(meters)
            meters.append(
                Meter(
                    meter_id=f"M-{n + 1:04d}",
                    msisdn=f"{MSISDN_PREFIX}{numbers[n]:08d}",
                    transformer_id=t.id,
                    suburb=suburb.name,
                    postcode=suburb.postcode,
                    lat=lat,
                    lon=lon,
                )
            )
    return Twin(seed, tuple(suburbs), tuple(transformers), tuple(meters))

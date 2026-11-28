"""Grid version of the digital twin (#6): suburbs, transformers and meters, built from one seed.

Every meter belongs to two groupings that overlap but don't match:
  - a transformer (power): if it fails, all its meters go silent together;
  - a suburb (network): Telstra reports outages by suburb, so a network fault silences a suburb.
Transformer areas near a suburb border spill into the next suburb. That mismatch is what lets the
engine tell a power outage from a network outage.

The suburbs are real: Coburg, Brunswick, Brunswick West and Pascoe Vale South, four neighbouring
Melbourne suburbs, from the ABS's Suburbs and Localities (SAL) 2021 boundaries (#26). The shapes in
data/suburbs.geojson were queried from the ABS ASGS 2021 SAL map service and simplified to about
10 m, which keeps the file small. Source: Australian Bureau of Statistics, Australian Statistical
Geography Standard (ASGS) Edition 3, licensed under CC BY 4.0.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from importlib import resources

N_TRANSFORMERS = 20
METERS_PER_TRANSFORMER = (50, 150)  # inclusive range, drawn per transformer
METER_SPREAD_M = 300  # standard deviation of the meter scatter around its transformer
TRANSFORMER_EDGE_MARGIN_M = 150  # keep transformers at least this far inside a suburb
TRANSFORMER_MIN_GAP_M = 600  # no two transformers closer than this
MSISDN_PREFIX = "614"  # Australian mobiles: 61 4xx xxx xxx, 11 digits in total

Point = tuple[float, float]  # (lon, lat), the order GeoJSON uses


def _load_shapes() -> list[dict]:
    text = resources.files("twin").joinpath("data/suburbs.geojson").read_text("utf-8")
    return json.loads(text)["features"]


_SHAPES = _load_shapes()
_ALL_POINTS = [pt for f in _SHAPES for ring in f["geometry"]["coordinates"] for pt in ring]

# The box around all four suburbs (degrees). South is the more negative latitude.
NORTH = max(lat for _, lat in _ALL_POINTS)
SOUTH = min(lat for _, lat in _ALL_POINTS)
WEST = min(lon for lon, _ in _ALL_POINTS)
EAST = max(lon for lon, _ in _ALL_POINTS)

# One degree of latitude is about 111 km everywhere. One degree of longitude shrinks towards the
# poles by cos(latitude): about 88 km here. Converting metres to degrees separately for each axis
# keeps the meter clusters round instead of squashed.
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = M_PER_DEG_LAT * math.cos(math.radians((NORTH + SOUTH) / 2))


def _in_ring(lon: float, lat: float, ring: tuple[Point, ...]) -> bool:
    """Ray casting: count how many edges a line going east from the point crosses."""
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _edge_distance_m(lon: float, lat: float, ring: tuple[Point, ...]) -> float:
    """Distance from the point to the nearest edge of the ring, in metres."""
    best = math.inf
    px, py = lon * M_PER_DEG_LON, lat * M_PER_DEG_LAT
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        ax, ay, bx, by = (
            x1 * M_PER_DEG_LON,
            y1 * M_PER_DEG_LAT,
            x2 * M_PER_DEG_LON,
            y2 * M_PER_DEG_LAT,
        )
        dx, dy = bx - ax, by - ay
        t = (
            0.0
            if dx == dy == 0
            else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        )
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


@dataclass(frozen=True, slots=True)
class Suburb:
    name: str
    postcode: str
    sal_code: str  # ABS SAL 2021 code
    ring: tuple[Point, ...]  # the outline, (lon, lat) points
    # The suburb's bounding box, for quick checks and for drawing.
    south: float
    north: float
    west: float
    east: float

    def contains(self, lat: float, lon: float) -> bool:
        if not (self.south <= lat <= self.north and self.west <= lon <= self.east):
            return False
        return _in_ring(lon, lat, self.ring)

    def edge_distance_m(self, lat: float, lon: float) -> float:
        return _edge_distance_m(lon, lat, self.ring)


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


def make_suburbs() -> list[Suburb]:
    """The four real suburbs, from data/suburbs.geojson."""
    suburbs = []
    for f in _SHAPES:
        ring = tuple((float(lon), float(lat)) for lon, lat in f["geometry"]["coordinates"][0])
        props = f["properties"]
        suburbs.append(
            Suburb(
                props["name"],
                props["postcode"],
                props["sal_code_2021"],
                ring,
                south=min(lat for _, lat in ring),
                north=max(lat for _, lat in ring),
                west=min(lon for lon, _ in ring),
                east=max(lon for lon, _ in ring),
            )
        )
    return suburbs


def suburb_of(lat: float, lon: float, suburbs: list[Suburb]) -> Suburb | None:
    """The suburb containing this point, or None if it falls outside every suburb."""
    return next((s for s in suburbs if s.contains(lat, lon)), None)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in metres. A flat approximation, fine over a few kilometres."""
    return math.hypot((lat1 - lat2) * M_PER_DEG_LAT, (lon1 - lon2) * M_PER_DEG_LON)


def _place_transformers(rng: random.Random, suburbs: list[Suburb]) -> list[Transformer]:
    """Uniformly over the area, keeping only spots inside a real suburb (a little way from its
    edge) and far enough from the transformers already placed. Redrawing until a condition holds
    is called rejection sampling. Meters still scatter across suburb lines around each one."""
    placed: list[Transformer] = []
    attempts = 0
    while len(placed) < N_TRANSFORMERS:
        attempts += 1
        if attempts > 50_000:
            raise RuntimeError("could not space the transformers out; lower TRANSFORMER_MIN_GAP_M")
        lat = rng.uniform(SOUTH, NORTH)
        lon = rng.uniform(WEST, EAST)
        home = suburb_of(lat, lon, suburbs)
        if home is None or home.edge_distance_m(lat, lon) < TRANSFORMER_EDGE_MARGIN_M:
            continue
        if all(distance_m(lat, lon, t.lat, t.lon) >= TRANSFORMER_MIN_GAP_M for t in placed):
            placed.append(Transformer(f"T-{len(placed) + 1:02d}", lat, lon))
    return placed


def _scatter_point(
    rng: random.Random, t: Transformer, suburbs: list[Suburb]
) -> tuple[float, float, Suburb]:
    """A point near transformer t (normal scatter), redrawn if it lands outside every suburb.
    Without the redraw, a transformer near the outer edge would lose meters off the map."""
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
    transformers = _place_transformers(rng, suburbs)
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

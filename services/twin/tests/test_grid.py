from collections import Counter

import pytest

from twin.grid import (
    EAST,
    METERS_PER_TRANSFORMER,
    N_TRANSFORMERS,
    NORTH,
    SOUTH,
    TRANSFORMER_MIN_GAP_M,
    WEST,
    build_twin,
    distance_m,
    make_suburbs,
    suburb_of,
)

SEEDS = [0, 1, 7, 42, 123]


def test_grid_has_four_suburbs_covering_the_box():
    suburbs = make_suburbs()
    assert len(suburbs) == 4
    names = {s.name for s in suburbs}
    assert names == {"Pascoe Vale South", "Coburg", "Brunswick West", "Brunswick"}
    assert min(s.south for s in suburbs) == SOUTH
    assert max(s.east for s in suburbs) == EAST


def test_point_on_a_shared_border_belongs_to_exactly_one_suburb():
    suburbs = make_suburbs()
    mid_lat = (NORTH + SOUTH) / 2
    mid_lon = (WEST + EAST) / 2
    owners = [s for s in suburbs if s.contains(mid_lat, mid_lon)]
    assert len(owners) == 1


def test_point_outside_the_box_has_no_suburb():
    assert suburb_of(-37.0, 145.5, make_suburbs()) is None


def test_point_on_the_outer_north_edge_has_no_suburb():
    # Half-open intervals leave the box's own north and east edges outside every suburb.
    # build_twin redraws such points, so no meter can end up there.
    assert suburb_of(NORTH, (WEST + EAST) / 2, make_suburbs()) is None


# --- build_twin (#6) ---------------------------------------------------------------------------


def test_same_seed_gives_the_same_twin():
    assert build_twin(42) == build_twin(42)


def test_different_seeds_give_different_twins():
    assert build_twin(42) != build_twin(43)


@pytest.mark.parametrize("seed", SEEDS)
def test_twin_has_the_planned_size(seed):
    twin = build_twin(seed)
    low, high = METERS_PER_TRANSFORMER
    assert len(twin.transformers) == N_TRANSFORMERS
    per_transformer = Counter(m.transformer_id for m in twin.meters)
    assert set(per_transformer) == {t.id for t in twin.transformers}
    assert all(low <= n <= high for n in per_transformer.values())
    assert N_TRANSFORMERS * low <= len(twin.meters) <= N_TRANSFORMERS * high


@pytest.mark.parametrize("seed", SEEDS)
def test_ids_and_phone_numbers_are_unique(seed):
    twin = build_twin(seed)
    assert len({m.meter_id for m in twin.meters}) == len(twin.meters)
    assert len({m.msisdn for m in twin.meters}) == len(twin.meters)
    assert all(m.msisdn.startswith("614") and len(m.msisdn) == 11 for m in twin.meters)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_meter_sits_inside_its_recorded_suburb(seed):
    twin = build_twin(seed)
    by_name = {s.name: s for s in twin.suburbs}
    for m in twin.meters:
        suburb = by_name[m.suburb]
        assert suburb.contains(m.lat, m.lon)
        assert m.postcode == suburb.postcode


@pytest.mark.parametrize("seed", SEEDS)
def test_transformers_are_spaced_apart(seed):
    ts = build_twin(seed).transformers
    for i, a in enumerate(ts):
        for b in ts[i + 1 :]:
            assert distance_m(a.lat, a.lon, b.lat, b.lon) >= TRANSFORMER_MIN_GAP_M


@pytest.mark.parametrize("seed", SEEDS)
def test_power_areas_cross_suburb_borders(seed):
    # The key property of the twin: if transformer areas matched suburbs exactly, a power outage
    # and a network outage would silence the same meters and the engine could never tell them
    # apart. Several transformers must feed meters in more than one suburb.
    twin = build_twin(seed)
    crossing = [t for t in twin.transformers if len({m.suburb for m in twin.meters_on(t.id)}) > 1]
    assert len(crossing) >= 3


@pytest.mark.parametrize("seed", SEEDS)
def test_every_suburb_has_meters(seed):
    twin = build_twin(seed)
    assert {m.suburb for m in twin.meters} == {s.name for s in twin.suburbs}

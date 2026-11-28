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


def test_four_real_neighbouring_suburbs_from_the_abs():
    suburbs = make_suburbs()
    assert {(s.name, s.postcode, s.sal_code) for s in suburbs} == {
        ("Coburg", "3058", "20596"),
        ("Brunswick", "3056", "20361"),
        ("Brunswick West", "3055", "20363"),
        ("Pascoe Vale South", "3044", "22042"),
    }
    assert min(s.south for s in suburbs) == SOUTH
    assert max(s.east for s in suburbs) == EAST


def test_landmarks_fall_in_the_right_suburb():
    suburbs = make_suburbs()
    # Coburg's town centre on Sydney Road, and Brunswick's around Sydney Road / Victoria St.
    assert suburb_of(-37.7440, 144.9630, suburbs).name == "Coburg"
    assert suburb_of(-37.7680, 144.9610, suburbs).name == "Brunswick"
    assert suburb_of(-37.7650, 144.9420, suburbs).name == "Brunswick West"
    assert suburb_of(-37.7440, 144.9370, suburbs).name == "Pascoe Vale South"


def test_neighbours_share_a_border_without_overlapping():
    suburbs = make_suburbs()
    # A grid of points over the area: none may be inside two suburbs.
    for i in range(40):
        for j in range(40):
            lat = SOUTH + (NORTH - SOUTH) * (i + 0.5) / 40
            lon = WEST + (EAST - WEST) * (j + 0.5) / 40
            assert sum(s.contains(lat, lon) for s in suburbs) <= 1


def test_point_outside_the_area_has_no_suburb():
    assert suburb_of(-37.0, 145.5, make_suburbs()) is None
    assert suburb_of(NORTH + 0.01, (WEST + EAST) / 2, make_suburbs()) is None


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

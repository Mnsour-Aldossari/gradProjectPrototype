import math

import pytest

from app.simulation import DEMO_AREA, SOIL_PROFILES, ObjectKind, plan_survey
from app.simulation.geo import point_in_polygon
from app.simulation.scenario import MIN_SEPARATION_M, generate_scenario

AREA_XY = plan_survey(DEMO_AREA, 2.0).area_xy


@pytest.mark.parametrize("soil", list(SOIL_PROFILES))
@pytest.mark.parametrize("seed", range(20))
def test_scenario_has_5_to_8_well_separated_objects_of_every_kind(soil, seed):
    sc = generate_scenario(AREA_XY, soil, seed)
    assert 5 <= len(sc.objects) <= 8
    assert {o.kind for o in sc.objects} >= set(ObjectKind)
    for o in sc.objects:
        assert point_in_polygon(o.x, o.y, AREA_XY)
    for i, a in enumerate(sc.objects):
        for b in sc.objects[i + 1 :]:
            assert math.hypot(a.x - b.x, a.y - b.y) >= MIN_SEPARATION_M


def test_same_seed_gives_same_scenario_and_different_seed_does_not():
    assert generate_scenario(AREA_XY, "dry_sand", 3) == generate_scenario(AREA_XY, "dry_sand", 3)
    assert generate_scenario(AREA_XY, "dry_sand", 3).objects != generate_scenario(AREA_XY, "dry_sand", 4).objects


def test_targets_are_only_mines():
    sc = generate_scenario(AREA_XY, "dry_sand", 1)
    for o in sc.objects:
        assert o.is_target == (o.kind in (ObjectKind.METAL_MINE, ObjectKind.LOW_METAL_MINE))


def test_soils_differ_in_the_way_that_affects_the_sensors():
    sand, clay, rocky = SOIL_PROFILES["dry_sand"], SOIL_PROFILES["wet_clay"], SOIL_PROFILES["mineralized_rocky"]
    assert clay.moisture > sand.moisture and clay.gpr_attenuation > sand.gpr_attenuation
    assert rocky.md_background > sand.md_background and rocky.md_noise > sand.md_noise


def test_unknown_soil_and_tiny_area_are_rejected():
    with pytest.raises(ValueError):
        generate_scenario(AREA_XY, "lava", 1)
    tiny = [(0, 0), (8, 0), (8, 8), (0, 8)]
    with pytest.raises(ValueError):
        generate_scenario(tiny, "dry_sand", 1)

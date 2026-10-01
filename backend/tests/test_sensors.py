import math

from app.simulation import SOIL_PROFILES, ObjectKind
from app.simulation.scenario import BuriedObject, FieldComponent, Scenario, SmoothField
from app.simulation.sensors import SensorModel, gpr_response, md_response, two_way_travel_time_ns

SAND = SOIL_PROFILES["dry_sand"]
CLAY = SOIL_PROFILES["wet_clay"]

METAL_MINE = BuriedObject(1, ObjectKind.METAL_MINE, 0, 0, depth_m=0.10, metal_mass=1.0, size_m=0.25, permittivity=None)
LOW_METAL_MINE = BuriedObject(
    2, ObjectKind.LOW_METAL_MINE, 0, 0, depth_m=0.07, metal_mass=0.006, size_m=0.11, permittivity=2.5
)
FLAT = SmoothField((FieldComponent(0, 0, 0, 1),))


def scenario(soil, *objects):
    return Scenario(seed=0, soil=soil, objects=objects, md_field=FLAT, gpr_field=FLAT)


def test_metal_response_weakens_with_altitude():
    values = [md_response(METAL_MINE, 0, 0, h) for h in (0.5, 1.0, 1.5, 2.5, 4.0)]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_metal_response_weakens_with_depth():
    values = [
        md_response(BuriedObject(1, ObjectKind.METAL_MINE, 0, 0, d, 1.0, 0.25, None), 0, 0, 1.5)
        for d in (0.0, 0.1, 0.2, 0.4)
    ]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_metal_response_weakens_with_horizontal_distance():
    values = [md_response(METAL_MINE, r, 0, 1.5) for r in (0.0, 0.5, 1.0, 2.0)]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_radar_return_weakens_in_wet_soil():
    assert gpr_response(METAL_MINE, CLAY, 0, 0, 1.5) < gpr_response(METAL_MINE, SAND, 0, 0, 1.5)


def test_radar_return_weakens_with_depth_faster_in_wet_soil():
    def depth_ratio(soil):
        shallow = BuriedObject(1, ObjectKind.METAL_MINE, 0, 0, 0.05, 1.0, 0.25, None)
        deep = BuriedObject(1, ObjectKind.METAL_MINE, 0, 0, 0.25, 1.0, 0.25, None)
        return gpr_response(deep, soil, 0, 0, 1.5) / gpr_response(shallow, soil, 0, 0, 1.5)

    assert depth_ratio(CLAY) < depth_ratio(SAND) < 1


def test_low_metal_mine_is_nearly_invisible_to_metal_detector_but_visible_to_radar():
    md = md_response(LOW_METAL_MINE, 0, 0, 1.5)
    gpr = gpr_response(LOW_METAL_MINE, SAND, 0, 0, 1.5)
    assert md < SAND.md_noise  # below the metal detector's own noise
    assert gpr > SAND.gpr_clutter + 4 * SAND.gpr_noise  # clearly above the radar background


def test_sensor_model_reports_reflector_depth_as_travel_time():
    model = SensorModel(scenario(SAND, METAL_MINE), noise_seed=1)
    samples = [model.sample(0, 0, 1.5) for _ in range(50)]
    expected = two_way_travel_time_ns(METAL_MINE.depth_m, SAND.permittivity)
    mean_twt = sum(s.gpr_twt_ns for s in samples) / len(samples)
    assert math.isclose(mean_twt, expected, abs_tol=0.05)


def test_sensor_model_background_only_away_from_objects():
    model = SensorModel(scenario(SAND, METAL_MINE), noise_seed=1)
    far = [model.sample(30, 30, 1.5) for _ in range(200)]
    near = [model.sample(0, 0, 1.5) for _ in range(200)]
    assert max(s.md for s in far) < min(s.md for s in near)
    assert all(s.md >= 0 and s.gpr_amp >= 0 for s in far + near)

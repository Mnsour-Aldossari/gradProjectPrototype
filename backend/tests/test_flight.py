import math
import random

import pytest

from app.simulation import DEMO_AREA, SimulationConfig, build_simulation, plan_survey
from app.simulation.flight import fly, lawnmower_path, path_length
from app.simulation.geo import LocalFrame, bounding_box

BBOX = (0.0, 0.0, 60.0, 40.0)


def test_lawnmower_lines_cover_the_whole_box():
    spacing = 2.0
    waypoints = lawnmower_path(BBOX, spacing)
    line_ys = sorted({y for _, y in waypoints})
    rng = random.Random(0)
    for _ in range(500):
        y = rng.uniform(BBOX[1], BBOX[3])
        assert min(abs(y - ly) for ly in line_ys) <= spacing / 2 + 1e-9
    assert all(BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3] for x, y in waypoints)


def test_lawnmower_alternates_direction():
    waypoints = lawnmower_path(BBOX, 10.0)
    assert waypoints[0][0] == BBOX[0] and waypoints[1][0] == BBOX[2]
    assert waypoints[2][0] == BBOX[2] and waypoints[3][0] == BBOX[0]


def test_flight_follows_path_at_constant_speed():
    waypoints = lawnmower_path(BBOX, 5.0)
    samples = list(fly(waypoints, 1.5, 2.0, 0.2, battery_drain_pct_per_s=0.1, rng=random.Random(1)))

    assert samples[0].progress == 0.0
    assert samples[-1].progress == pytest.approx(1.0)
    assert all(b.t_s > a.t_s for a, b in zip(samples, samples[1:]))
    assert all(b.battery_pct < a.battery_pct for a, b in zip(samples, samples[1:]))
    assert samples[-1].t_s == pytest.approx(path_length(waypoints) / 2.0, abs=0.2)
    for a, b in zip(samples, samples[1:-1]):
        assert math.hypot(b.x - a.x, b.y - a.y) <= 2.0 * 0.2 + 1e-9
    assert all(abs(s.alt_m - 1.5) < 0.2 for s in samples)


def test_heading_matches_direction_of_travel():
    samples = list(fly([(0, 0), (10, 0), (10, 10)], 1.5, 2.0, 0.2, battery_drain_pct_per_s=0, rng=random.Random(1)))
    assert samples[1].heading_deg == pytest.approx(90.0)  # flying east
    assert samples[-2].heading_deg == pytest.approx(0.0)  # flying north


def test_local_frame_round_trip():
    frame = LocalFrame.centred_on(DEMO_AREA)
    for lat, lon in DEMO_AREA:
        x, y = frame.to_xy(lat, lon)
        lat2, lon2 = frame.to_latlon(x, y)
        assert lat2 == pytest.approx(lat, abs=1e-9) and lon2 == pytest.approx(lon, abs=1e-9)


def test_demo_area_is_about_60_by_40_metres():
    plan = plan_survey(DEMO_AREA, 2.0)
    assert plan.width_m == pytest.approx(60, abs=2)
    assert plan.height_m == pytest.approx(40, abs=2)
    xmin, ymin, xmax, ymax = bounding_box(plan.area_xy)
    assert all(xmin <= x <= xmax and ymin <= y <= ymax for x, y in plan.waypoints_xy)


def test_simulation_is_deterministic_for_a_seed():
    cfg = SimulationConfig(area=DEMO_AREA, altitude_m=1.5, speed_mps=3, line_spacing_m=2.5, soil_type="wet_clay", seed=5)
    first = list(build_simulation(cfg).samples())
    second = list(build_simulation(cfg).samples())
    assert first == second


def _circle(cx, cy, r, n=32):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def test_lanes_for_a_rectangle_are_the_lawnmower_path():
    """Rectangles (every mission so far, the evaluation and the demo) fly exactly the same path as before."""
    from app.simulation.flight import survey_lanes

    rect = [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]
    for spacing in (0.5, 2.0, 2.5, 5.0):
        assert survey_lanes(rect, spacing) == lawnmower_path(BBOX, spacing)


def test_lanes_stay_inside_a_circle_and_cover_it():
    from app.simulation.flight import survey_lanes
    from app.simulation.geo import point_in_polygon

    circle = _circle(0, 0, 30)
    spacing = 2.0
    waypoints = survey_lanes(circle, spacing)
    for (x0, y0), (x1, y1) in zip(waypoints[::2], waypoints[1::2]):
        assert y0 == y1
        assert point_in_polygon((x0 + x1) / 2, y0, circle)  # each lane piece lies inside
    assert path_length(waypoints) < 0.85 * path_length(lawnmower_path((-30, -30, 30, 30), spacing))
    line_ys = sorted({y for _, y in waypoints})
    rng = random.Random(0)
    for _ in range(500):  # every point inside, away from the very top and bottom, is near a lane
        x, y = rng.uniform(-30, 30), rng.uniform(-28, 28)
        if point_in_polygon(x, y, circle):
            assert min(abs(y - ly) for ly in line_ys) <= spacing / 2 + 1e-9


def test_concave_outline_flies_each_piece_of_a_lane():
    from app.simulation.flight import survey_lanes

    u_shape = [(0, 0), (60, 0), (60, 40), (40, 40), (40, 15), (20, 15), (20, 40), (0, 40)]
    upper = [w for w in survey_lanes(u_shape, 5.0) if w[1] > 15]
    assert all(not (20 < x < 40) for x, _ in upper)  # nothing ends in the gap of the U
    assert {x for x, _ in upper} == {0, 20, 40, 60}


def test_outline_that_crosses_itself_is_found():
    from app.simulation.geo import is_simple

    assert is_simple([(0, 0), (60, 0), (60, 40), (0, 40)])
    assert is_simple(_circle(0, 0, 30))
    assert not is_simple([(0, 0), (60, 40), (60, 0), (0, 40)])  # a bow tie

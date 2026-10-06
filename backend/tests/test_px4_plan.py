"""The PX4 source's pure parts (app/uav/px4_plan.py), without a vehicle."""

from __future__ import annotations

import math

import pytest

from app.simulation import DEMO_AREA, SimulationConfig, build_simulation
from app.uav.px4_plan import (
    ACCEPTANCE_RADIUS_M,
    PathProgress,
    Px4State,
    WaypointTracker,
    build_frame,
    distance_m,
    home_check,
    survey_waypoints,
)

CONFIG = SimulationConfig(
    area=DEMO_AREA, altitude_m=1.5, speed_mps=2.0, line_spacing_m=2.0, soil_type="dry_sand", seed=2000
)


@pytest.fixture(scope="module")
def sim():
    return build_simulation(CONFIG)


def state(sim, x, y, current, **overrides) -> Px4State:
    lat, lon = sim.frame.to_latlon(x, y)
    values = dict(
        lat_deg=lat, lon_deg=lon, absolute_alt_m=431.5, relative_alt_m=1.5, v_north_m_s=0.0, v_east_m_s=2.0,
        v_down_m_s=0.0, heading_deg=90.0, battery_pct=87.4, current=current, total=len(sim.plan.waypoints_xy),
    )
    values.update(overrides)
    return Px4State(**values)


def test_waypoints_are_the_simulators_path_at_the_missions_height_and_speed(sim):
    wps = survey_waypoints(sim)
    assert [(w.lat, w.lon) for w in wps] == sim.plan.waypoints_latlon
    assert {(w.relative_alt_m, w.speed_m_s) for w in wps} == {(1.5, 2.0)}
    assert ACCEPTANCE_RADIUS_M < CONFIG.line_spacing_m / 2


def test_home_near_the_area_is_accepted_and_a_far_one_explained(sim):
    wps = survey_waypoints(sim)
    centre = (sum(p[0] for p in DEMO_AREA) / 4, sum(p[1] for p in DEMO_AREA) / 4)
    assert home_check(centre, wps) is None
    zurich = (47.397742, 8.545594)  # PX4 SITL's default home
    reason = home_check(zurich, wps)
    assert reason is not None and "PX4_HOME_LAT" in reason
    assert 3000 < distance_m(zurich, centre) / 1000 < 4000  # Al-Kharj to Zurich, about 3500 km


def test_progress_follows_the_path(sim):
    progress = PathProgress(sim.plan)
    pts = sim.plan.waypoints_xy
    (x0, y0), (x1, y1) = pts[0], pts[1]
    assert progress.fraction(x0, y0, 0) == 0.0  # still climbing to the first waypoint
    assert progress.fraction(x0, y0, 1) == 0.0
    half_lane = progress.fraction((x0 + x1) / 2, (y0 + y1) / 2, 1)
    assert half_lane == pytest.approx(math.dist(pts[0], pts[1]) / 2 / sim.plan.length_m)
    # Overshooting a lane end (or drifting before its start) stays within the lane.
    assert progress.fraction(x1 + 3, y1, 1) == pytest.approx(math.dist(pts[0], pts[1]) / sim.plan.length_m)
    assert progress.fraction(x0 - 3, y0, 1) == 0.0
    assert progress.fraction(*pts[-1], len(pts)) == 1.0


def test_frame_carries_px4_values_in_mavlink_units(sim):
    x, y = sim.plan.waypoints_xy[0]
    f = build_frame(state(sim, x, y, 1, heading_deg=359.996), 12.34, sim, PathProgress(sim.plan))
    p = f.position
    assert p.time_boot_ms == 12340
    assert (p.relative_alt, p.alt) == (1500, 431500)
    assert (p.vx, p.vy, p.vz) == (0, 200, 0)
    assert p.hdg == 0  # 359.996 deg rounds to 36000 cdeg, which wraps to 0
    assert f.battery.battery_remaining == 87
    assert (f.mission.seq, f.mission.total) == (1, len(sim.plan.waypoints_xy))


def test_sensor_readings_only_on_the_survey_lines(sim):
    x, y = sim.plan.waypoints_xy[0]
    progress = PathProgress(sim.plan)
    total = len(sim.plan.waypoints_xy)
    assert build_frame(state(sim, x, y, 0), 1, sim, progress).sensor is None  # takeoff
    assert build_frame(state(sim, x, y, total), 1, sim, progress).sensor is None  # finished, on the way home
    on_line = build_frame(state(sim, x, y, 1), 1, sim, progress).sensor
    assert on_line is not None and on_line.md >= 0 and on_line.gpr_amp >= 0


def test_sensors_see_the_buried_objects_at_px4_position(sim):
    """Over a metal object the metal detector reads clearly more than over open ground."""
    progress = PathProgress(sim.plan)
    metal = max(sim.scenario.objects, key=lambda o: o.metal_mass)
    over = build_frame(state(sim, metal.x, metal.y, 1), 1, sim, progress).sensor.md
    away = [build_frame(state(sim, metal.x + 15, metal.y, 1), 1, sim, progress).sensor.md for _ in range(5)]
    assert over > 3 * max(away)


def walk(points, step_m=0.2):
    """Positions every step_m along the waypoints, as PX4 would report them flying the path."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        n = max(1, int(math.dist((x0, y0), (x1, y1)) / step_m))
        for k in range(n):
            yield x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
    yield points[-1]


def test_tracker_follows_the_waypoints_in_order(sim):
    tracker = WaypointTracker(sim.plan)
    seen = [tracker.update(x, y) for x, y in walk(sim.plan.waypoints_xy)]
    assert seen == sorted(seen)  # never goes back
    assert set(seen) == set(range(1, tracker.total + 1))  # every waypoint, none skipped
    assert seen[-1] == tracker.total  # the last one reached: finished


def test_tracker_waits_for_the_vehicle_to_arrive(sim):
    tracker = WaypointTracker(sim.plan)
    x0, y0 = sim.plan.waypoints_xy[0]
    assert tracker.update(x0 - 5, y0) == 0  # taking off away from the first waypoint
    assert tracker.update(x0 - 0.3, y0) == 1  # within the acceptance radius
    assert tracker.update(x0 - 0.3, y0) == 1  # hovering there does not skip the lane


def test_tracker_on_closely_spaced_lanes():
    tight = build_simulation(
        SimulationConfig(area=DEMO_AREA, altitude_m=1.5, speed_mps=2.0, line_spacing_m=0.5, soil_type="dry_sand", seed=1)
    )
    tracker = WaypointTracker(tight.plan)
    assert tracker.arrival_m < 0.25  # less than half the 0.5 m gap between lane ends
    seen = [tracker.update(x, y) for x, y in walk(tight.plan.waypoints_xy, step_m=0.1)]
    assert set(seen) == set(range(1, tracker.total + 1))


def test_tracker_follows_a_mission_resumed_part_way(sim):
    """PX4 resumed an interrupted identical mission at a later lane: the tracker picks it up there."""
    tracker = WaypointTracker(sim.plan)
    later = sim.plan.waypoints_xy[4:]
    seen = [tracker.update(x, y) for x, y in walk(later)]
    assert seen[0] == 5 and seen[-1] == tracker.total


def test_no_readings_while_paused_or_on_the_way_down(sim):
    """Hovering over one spot would pile readings there, and the payload does not scan on the way home."""
    x, y = sim.plan.waypoints_xy[0]
    frame = build_frame(state(sim, x, y, 1), 1, sim, PathProgress(sim.plan), scanning=False)
    assert frame.sensor is None

"""The parts of the nodes that need no ROS graph: the survey frame and the detector fed reading by reading."""

import math

from uav_landmine_ros.core import DetectorCore, MissionParams, SurveyFrame, import_detection, rounded

import_detection()  # puts the project's backend on the path for the imports below

from app.evaluation.harness import simulate_scenario  # noqa: E402
from app.evaluation.protocol import STANDARD_SURVEY  # noqa: E402
from app.simulation import DEMO_AREA  # noqa: E402
from app.simulation.geo import LocalFrame  # noqa: E402
from app.detection import detect_adaptive  # noqa: E402


def test_the_survey_frame_is_the_backends():
    ours, theirs = SurveyFrame.centred_on([list(p) for p in DEMO_AREA]), LocalFrame.centred_on(DEMO_AREA)
    for lat, lon in [*DEMO_AREA, (24.1395, 47.262)]:
        assert ours.to_xy(lat, lon) == theirs.to_xy(lat, lon)
    assert ours.to_latlon(12.5, -7.25) == theirs.to_latlon(12.5, -7.25)


def mission(soil: str) -> MissionParams:
    return MissionParams(1, soil, STANDARD_SURVEY["altitude_m"], STANDARD_SURVEY["speed_mps"],
                         STANDARD_SURVEY["line_spacing_m"], tuple(DEMO_AREA))  # fmt: skip


def test_fed_one_by_one_it_finds_what_the_backends_detector_finds():
    for soil, seed in (("dry_sand", 2000), ("wet_clay", 77)):
        run = simulate_scenario(soil, seed)
        core = DetectorCore(mission(soil))
        looks = 0
        for i, r in enumerate(run.readings, start=1):
            if core.add(i, r.t_s, r.x, r.y, r.alt_m, r.md, r.gpr_amp, r.gpr_twt_ns):
                looks += 1
                core.found()  # as the node publishes on the way
        assert looks == len(run.readings) // 25
        assert not core.add(5, 0, 0, 0, 1.5, 9.9, 9.9, 1.0)  # a reading already taken is ignored
        found = core.found()
        expected = detect_adaptive(run.readings, run.context)
        assert found and [(f.category, f.n_hits, f.confidence, f.x_m, f.y_m) for f in found] == [
            (c.category.value, c.n_hits, c.confidence, c.x, c.y) for c in expected
        ]
        for f in found:
            x, y = core.frame.to_xy(f.latitude, f.longitude)
            assert math.isclose(x, f.x_m, abs_tol=1e-6) and math.isclose(y, f.y_m, abs_tol=1e-6)


def test_detections_are_compared_as_the_backend_stores_them():
    assert rounded("high", 0.85049, 7, 24.1, 47.2) == ("high", 7, 0.85, 24.1, 47.2)

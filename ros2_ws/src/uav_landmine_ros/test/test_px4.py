"""PX4 read over uXRCE-DDS against the backend's MAVLink view (px4_core), without ROS or PX4."""

import pytest

from uav_landmine_ros.core import SurveyFrame
from uav_landmine_ros.px4_core import AGREE_M, Fix, Track, backend_flight, compare, distance_m, nav_state_name

FRAME = SurveyFrame(24.1395, 47.262)


def at(x: float, y: float, t: float = 0.0, alt: float = 600.0) -> Fix:
    lat, lon = FRAME.to_latlon(x, y)
    return Fix(t, lat, lon, alt)


def backend_point(x: float, y: float, alt: float = 600.0) -> dict:
    lat, lon = FRAME.to_latlon(x, y)
    return {"lat": lat, "lon": lon, "alt_msl_m": alt}


def flying_mission(status="running", phase="surveying"):
    return {"id": 5, "status": status, "phase": phase}


def test_mode_names_and_ground_distance():
    assert (nav_state_name(3), nav_state_name(5), nav_state_name(18), nav_state_name(99)) == (
        "auto_mission", "auto_rtl", "auto_land", "mode_99")  # fmt: skip
    a, b = at(0, 0), at(3, 4)
    assert distance_m(a.lat, a.lon, b.lat, b.lon) == pytest.approx(5.0, abs=1e-3)


def test_the_track_keeps_ten_seconds_and_measures_to_its_segments():
    track = Track(kept_s=10)
    for t in range(0, 21, 2):  # flying east at 2 m/s
        track.add(at(2.0 * t, 0, t))
    assert track.latest.t == 20
    p = backend_point(25.0, 0.5)  # 2.5 s behind, half a metre off the line
    assert track.distance_m(p["lat"], p["lon"]) == pytest.approx(0.5, abs=1e-3)
    old = backend_point(4.0, 0)  # from t = 2 s: no longer on the track kept
    assert track.distance_m(old["lat"], old["lon"]) == pytest.approx(16.0, abs=1e-3)


def test_what_the_backend_says_of_the_uav():
    assert backend_flight(flying_mission()) == "flying"
    assert backend_flight(flying_mission(phase="returning")) == "flying"
    assert backend_flight(flying_mission(phase="landing")) == ""
    assert backend_flight(flying_mission("completed", None)) == "down"
    assert backend_flight(None) == ""


def test_px4_and_the_backend_agree_when_the_backend_lags_on_the_same_track():
    track = Track()
    for t in range(10):
        track.add(at(5.0 * t, 0, t))
    result = compare(track, False, flying_mission(), backend_point(37.0, 0.3))
    assert result.ok and result.values["position_difference_m"] == pytest.approx(0.3, abs=0.01)
    assert (result.values["backend_says"], result.values["px4_says"]) == ("flying", "flying")


def test_a_position_too_far_or_a_landing_not_agreed_is_a_warning():
    track = Track()
    track.add(at(0, 0, 0))
    far = compare(track, False, flying_mission(), backend_point(0, AGREE_M + 1.0))
    assert not far.ok and far.warn and "apart" in far.message
    down = compare(track, True, flying_mission(), backend_point(0, 0))
    assert not down.ok and "the backend says flying, PX4 says down" in down.message
    landed = compare(track, True, flying_mission("completed", None), backend_point(0, 0))
    assert landed.ok


def test_nothing_from_px4_is_an_error_and_no_mission_is_fine():
    assert not compare(Track(), None, flying_mission(), backend_point(0, 0)).warn
    track = Track()
    track.add(at(0, 0))
    assert compare(track, None, None, None).ok

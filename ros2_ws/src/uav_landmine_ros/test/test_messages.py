"""Messages built from what the backend sends."""

import math

from builtin_interfaces.msg import Time
from visualization_msgs.msg import Marker

from uav_landmine_ros import messages
from uav_landmine_ros.core import SurveyFrame

AREA = [[24.13968, 47.2617], [24.13968, 47.2623], [24.13932, 47.2623], [24.13932, 47.2617]]
FRAME = SurveyFrame.centred_on(AREA)
STAMP = Time(sec=1)


def test_a_reading_keeps_the_backends_values_exactly():
    r = {"id": 9, "t_s": 12.4, "lat": 24.1395, "lon": 47.262, "x_m": 1.25, "y_m": -3.5, "relative_alt_m": 1.5,
         "md": 0.123456789, "gpr_amp": 0.0123456789, "gpr_twt_ns": 1.75}  # fmt: skip
    msg = messages.sensor_reading(r, 3, STAMP)
    assert (msg.mission_id, msg.id, msg.md, msg.gpr_amp, msg.x_m) == (3, 9, r["md"], r["gpr_amp"], 1.25)
    assert msg.header.frame_id == "survey"


def test_a_backend_detection_without_depth_and_its_place_in_the_survey_frame():
    d = {"id": 4, "method": "adaptive", "category": "high", "lat": 24.1395, "lon": 47.262, "confidence": 0.85,
         "peak_md": 0.9, "peak_gpr": 0.3, "est_depth_m": None, "n_hits": 7, "explanation": "x",
         "status": "pending"}  # fmt: skip
    msg = messages.backend_detection(d, FRAME)
    assert math.isnan(msg.est_depth_m) and msg.category_label == "High priority"
    assert (msg.x_m, msg.y_m) == FRAME.to_xy(24.1395, 47.262)


def test_the_pose_faces_where_the_uav_heads():
    t = {"lat": 24.1395, "lon": 47.262, "relative_alt_m": 1.5, "heading_deg": 0.0}
    north = messages.pose(t, FRAME, STAMP).pose.orientation
    assert math.isclose(2 * math.atan2(north.z, north.w), math.pi / 2)  # north is +y
    east = messages.pose({**t, "heading_deg": 90.0}, FRAME, STAMP).pose.orientation
    assert math.isclose(2 * math.atan2(east.z, east.w), 0.0, abs_tol=1e-12)


def test_markers():
    area = messages.area_marker({"area": AREA}, FRAME, STAMP)
    assert len(area.points) == 5 and (area.points[0].x, area.points[0].y) == (area.points[-1].x, area.points[-1].y)
    readings = messages.readings_marker([(0.0, 0.0, 0.0), (1.0, 0.0, 2.0)], STAMP)
    assert readings.colors[0].b > readings.colors[1].b  # pale for a weak reading, dark for a strong one
    found = messages.detection_markers([], "x", STAMP)
    assert [m.action for m in found] == [Marker.DELETEALL]


def test_transforms_place_the_uav_in_the_survey_frame():
    t = {"lat": 24.1395, "lon": 47.262, "relative_alt_m": 1.5, "heading_deg": 90.0}
    tf = messages.uav_transform(messages.pose(t, FRAME, STAMP))
    assert (tf.header.frame_id, tf.child_frame_id) == ("survey", "uav")
    assert (tf.transform.translation.x, tf.transform.translation.y) == FRAME.to_xy(24.1395, 47.262)
    assert tf.transform.translation.z == 1.5
    static = messages.map_transform(STAMP)
    assert (static.header.frame_id, static.child_frame_id, static.transform.rotation.w) == ("map", "survey", 1.0)


def test_diagnostics_say_ok_warn_or_error():
    from diagnostic_msgs.msg import DiagnosticStatus

    ok = messages.diagnostic("x", True, "fine", {"readings": 3})
    assert ok.level == DiagnosticStatus.OK and ok.values[0].key == "readings" and ok.values[0].value == "3"
    assert messages.diagnostic("x", False, "late", {}, warn=True).level == DiagnosticStatus.WARN
    assert messages.diagnostic("x", False, "down", {}).level == DiagnosticStatus.ERROR

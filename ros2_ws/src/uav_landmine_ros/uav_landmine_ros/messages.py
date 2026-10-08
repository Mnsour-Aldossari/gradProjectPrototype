"""ROS messages built from what the backend sends (JSON) and from the detector node's candidates."""

from __future__ import annotations

import math

from builtin_interfaces.msg import Time
from geometry_msgs.msg import Point, PoseStamped
from sensor_msgs.msg import BatteryState, NavSatFix, NavSatStatus
from std_msgs.msg import ColorRGBA, Header
from uav_landmine_interfaces.msg import Detection, MissionInfo, SensorReading
from visualization_msgs.msg import Marker

from .core import SurveyFrame

FRAME = "survey"  # metres from the centre of the survey area, x east, y north, z up
CATEGORY_LABELS = {"high": "High priority", "suspect": "Needs verification", "clutter": "Likely clutter"}
# The web map's colours (web/src/theme.ts).
CATEGORY_COLOURS = {"high": "#c62d1f", "suspect": "#e0a526", "clutter": "#8a948c"}
HAZARD, SURVEY = "#c62d1f", "#1f5fad"


def header(stamp: Time, frame_id: str = FRAME) -> Header:
    return Header(stamp=stamp, frame_id=frame_id)


def colour(hex_colour: str, alpha: float = 1.0) -> ColorRGBA:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return ColorRGBA(r=r, g=g, b=b, a=alpha)


def mission_info(
    mission: dict, frame: SurveyFrame, sample_period_s: float, published: int, complete: bool
) -> MissionInfo:
    return MissionInfo(
        id=mission["id"],
        name=mission["name"],
        status=mission["status"],
        sensor_collection=mission.get("sensor_collection") or "",
        soil_type=mission["soil_type"],
        altitude_m=float(mission["altitude_m"]),
        speed_mps=float(mission["speed_mps"]),
        line_spacing_m=float(mission["line_spacing_m"]),
        sample_period_s=sample_period_s,
        origin_latitude=frame.lat0,
        origin_longitude=frame.lon0,
        area_latitude=[float(p[0]) for p in mission["area"]],
        area_longitude=[float(p[1]) for p in mission["area"]],
        progress=float(mission["progress"]),
        readings_published=published,
        readings_complete=complete,
    )


def sensor_reading(reading: dict, mission_id: int, stamp: Time) -> SensorReading:
    return SensorReading(
        header=header(stamp),
        mission_id=mission_id,
        id=reading["id"],
        t_s=reading["t_s"],
        latitude=reading["lat"],
        longitude=reading["lon"],
        x_m=reading["x_m"],
        y_m=reading["y_m"],
        height_m=reading["relative_alt_m"],
        md=reading["md"],
        gpr_amp=reading["gpr_amp"],
        gpr_twt_ns=reading["gpr_twt_ns"],
    )


def backend_detection(d: dict, frame: SurveyFrame) -> Detection:
    x, y = frame.to_xy(d["lat"], d["lon"])
    return Detection(
        id=d["id"],
        method=d["method"],
        category=d["category"],
        category_label=CATEGORY_LABELS.get(d["category"], d["category"]),
        latitude=d["lat"],
        longitude=d["lon"],
        x_m=x,
        y_m=y,
        confidence=d["confidence"],
        peak_md=d["peak_md"],
        peak_gpr=d["peak_gpr"],
        est_depth_m=math.nan if d["est_depth_m"] is None else d["est_depth_m"],
        n_hits=d["n_hits"],
        explanation=d["explanation"],
        status=d["status"],
    )


def found_detection(f) -> Detection:
    """f: core.Found."""
    return Detection(
        id=0,
        method="adaptive",
        category=f.category,
        category_label=CATEGORY_LABELS.get(f.category, f.category),
        latitude=f.latitude,
        longitude=f.longitude,
        x_m=f.x_m,
        y_m=f.y_m,
        confidence=f.confidence,
        peak_md=f.peak_md,
        peak_gpr=f.peak_gpr,
        est_depth_m=math.nan if f.est_depth_m is None else f.est_depth_m,
        n_hits=f.n_hits,
        explanation=f.explanation,
        status="",
    )


def nav_sat_fix(t: dict, stamp: Time) -> NavSatFix:
    return NavSatFix(
        header=header(stamp, "uav"),
        status=NavSatStatus(status=NavSatStatus.STATUS_FIX, service=NavSatStatus.SERVICE_GPS),
        latitude=t["lat"],
        longitude=t["lon"],
        altitude=t["alt_msl_m"],
        position_covariance_type=NavSatFix.COVARIANCE_TYPE_UNKNOWN,
    )


def pose(t: dict, frame: SurveyFrame, stamp: Time) -> PoseStamped:
    """Position in the survey frame; heading (degrees from north, clockwise) as a rotation about z."""
    msg = PoseStamped(header=header(stamp))
    msg.pose.position.x, msg.pose.position.y = frame.to_xy(t["lat"], t["lon"])
    msg.pose.position.z = t["relative_alt_m"]
    yaw = math.radians(90.0 - t["heading_deg"])
    msg.pose.orientation.z, msg.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
    return msg


def battery(t: dict, stamp: Time) -> BatteryState:
    return BatteryState(header=header(stamp, "uav"), percentage=t["battery_pct"] / 100.0, present=True)


def area_marker(mission: dict, frame: SurveyFrame, stamp: Time) -> Marker:
    m = Marker(header=header(stamp), ns="area", id=0, type=Marker.LINE_STRIP, action=Marker.ADD)
    m.scale.x = 0.25
    m.color = colour(HAZARD)
    for lat, lon in [*mission["area"], mission["area"][0]]:
        x, y = frame.to_xy(lat, lon)
        m.points.append(Point(x=x, y=y, z=0.0))
    return m


def detection_markers(detections: list[Detection], ns: str, stamp: Time) -> list[Marker]:
    """A disc on the ground per detection, coloured by category, with its number; replaces the namespace."""
    out = [Marker(header=header(stamp), ns=ns, action=Marker.DELETEALL)]
    for i, d in enumerate(detections):
        disc = Marker(header=header(stamp), ns=ns, id=2 * i + 1, type=Marker.CYLINDER, action=Marker.ADD)
        disc.pose.position.x, disc.pose.position.y, disc.pose.position.z = d.x_m, d.y_m, 0.05
        disc.pose.orientation.w = 1.0
        disc.scale.x = disc.scale.y = 0.6 if d.category != "clutter" else 0.4
        disc.scale.z = 0.1
        disc.color = colour(CATEGORY_COLOURS.get(d.category, "#ffffff"), 0.9)
        label = Marker(header=header(stamp), ns=ns, id=2 * i + 2, type=Marker.TEXT_VIEW_FACING, action=Marker.ADD)
        label.pose.position.x, label.pose.position.y, label.pose.position.z = d.x_m, d.y_m, 0.6
        label.pose.orientation.w = 1.0
        label.scale.z = 0.4
        label.color = colour("#ffffff")
        label.text = f"#{d.id} {d.category_label}" if d.id else d.category_label
        out += [disc, label]
    return out


def readings_marker(points: list[tuple[float, float, float]], stamp: Time) -> Marker:
    """The readings so far as points on the ground, pale to dark blue with the metal detector's value (1 = MD 1.0
    or more, the web heatmap's full scale)."""
    m = Marker(header=header(stamp), ns="readings_md", id=0, type=Marker.POINTS, action=Marker.ADD)
    m.scale.x = m.scale.y = 0.3
    pale, dark = colour("#cde2fb"), colour("#0d366b")
    for x, y, md in points:
        t = math.sqrt(min(1.0, max(0.0, md)))
        m.points.append(Point(x=x, y=y, z=0.0))
        r, g, b = (low + (high - low) * t for low, high in ((pale.r, dark.r), (pale.g, dark.g), (pale.b, dark.b)))
        m.colors.append(ColorRGBA(r=r, g=g, b=b, a=0.8))
    return m

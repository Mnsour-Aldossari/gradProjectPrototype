"""landmine_detector: the project's adaptive detector as a ROS 2 node.

Reads /mission/info and /sensors/readings, feeds every reading to the same detector the mission runner uses
(backend/app/detection, unchanged), and publishes its potential detections on /landmine/candidates (and markers on
/landmine/markers) every 25 readings and once more, final, when the mission has ended and every reading has come.
A real sensor publishing SensorReading messages could feed it the same way. Simulated data; every output is a
potential detection for trained personnel to verify.
"""

from __future__ import annotations

from rclpy.node import Node
from uav_landmine_interfaces.msg import DetectionArray, MissionInfo, SensorReading
from visualization_msgs.msg import MarkerArray

from . import messages
from .bridge import READINGS_KEPT, latched
from .core import DETECT_EVERY, DetectorCore, MissionParams
from .run import spin

WAIT_FOR_LAST_S = 5.0  # after the mission ended, how long to wait for readings still on their way


def mission_params(info: MissionInfo) -> MissionParams:
    return MissionParams(
        id=info.id,
        soil_type=info.soil_type,
        altitude_m=info.altitude_m,
        speed_mps=info.speed_mps,
        line_spacing_m=info.line_spacing_m,
        area=tuple(zip(info.area_latitude, info.area_longitude, strict=True)),
        sample_period_s=info.sample_period_s,
    )


class LandmineDetector(Node):
    def __init__(self) -> None:
        super().__init__("landmine_detector")
        self.declare_parameter("detect_every", DETECT_EVERY)
        self._every = int(self.get_parameter("detect_every").value)
        self._core: DetectorCore | None = None
        self._info: MissionInfo | None = None
        self._early: dict[int, list[SensorReading]] = {}  # readings that came before their mission
        self._finished = False
        self._waiting_since: float | None = None

        self._candidates = self.create_publisher(DetectionArray, "/landmine/candidates", latched())
        self._markers = self.create_publisher(MarkerArray, "/landmine/markers", latched(10))
        self.create_subscription(MissionInfo, "/mission/info", self._on_info, latched())
        self.create_subscription(SensorReading, "/sensors/readings", self._on_reading, latched(READINGS_KEPT))
        self.create_timer(1.0, self._check_end)
        self.get_logger().info("Waiting for /mission/info and /sensors/readings")

    def _on_info(self, info: MissionInfo) -> None:
        if self._core is None or self._core.mission.id != info.id:
            self._core = DetectorCore(mission_params(info), self._every)
            self._finished, self._waiting_since = False, None
            lanes = f"lanes {info.line_spacing_m:g} m"
            self.get_logger().info(f"Mission {info.id} ({info.name}): {info.soil_type}, {lanes}")
            for reading in self._early.pop(info.id, []):
                self._take(reading)
            self._early.clear()
        self._info = info
        self._check_end()

    def _on_reading(self, reading: SensorReading) -> None:
        if self._core is None or reading.mission_id != self._core.mission.id:
            self._early.setdefault(reading.mission_id, []).append(reading)
            return
        self._take(reading)
        self._check_end()

    def _take(self, r: SensorReading) -> None:
        if self._core.add(r.id, r.t_s, r.x_m, r.y_m, r.height_m, r.md, r.gpr_amp, r.gpr_twt_ns) and not self._finished:
            self._publish(final=False)

    def _check_end(self) -> None:
        """Final once the mission has ended and every reading the bridge sent has come; after a few seconds without
        them, final anyway, with a warning that the result may differ from the backend's."""
        info, core = self._info, self._core
        if self._finished or info is None or core is None or not info.readings_complete:
            return
        missing = info.readings_published - core.readings
        if missing > 0:
            now = self.get_clock().now().nanoseconds / 1e9
            self._waiting_since = self._waiting_since or now
            if now - self._waiting_since < WAIT_FOR_LAST_S:
                return
            self.get_logger().warning(f"{missing} readings never came: the result may differ from the backend's")
        self._finished = True
        found = self._publish(final=missing <= 0)
        counts = {c: sum(f.category == c for f in found) for c in ("high", "suspect", "clutter")}
        self.get_logger().info(
            f"Mission {info.id}: {core.readings} readings, {counts['high']} high priority, {counts['suspect']} "
            f"needs verification, {counts['clutter']} likely clutter (potential detections)"
        )

    def _publish(self, final: bool) -> list:
        found = self._core.found()
        stamp = self.get_clock().now().to_msg()
        detections = [messages.found_detection(f) for f in found]
        self._candidates.publish(
            DetectionArray(
                header=messages.header(stamp), source="ros_detector", mission_id=self._core.mission.id, final=final,
                detections=detections,
            )
        )  # fmt: skip
        self._markers.publish(MarkerArray(markers=messages.detection_markers(detections, "ros_detector", stamp)))
        return found


def main(args=None) -> None:
    spin(LandmineDetector, args=args)

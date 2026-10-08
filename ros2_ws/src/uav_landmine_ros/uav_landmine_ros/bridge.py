"""mission_bridge: follows a mission in the backend and publishes it on ROS 2 topics.

It only reads: the backend flies the mission (simulator or PX4) and stores it as before. Every reading is published,
in the order it was taken (paged from GET /api/missions/{id}/readings), so a detector on the ROS side sees what the
mission runner saw. Simulated data; detections are potential ones for trained personnel to verify.

Topics (frame "survey": metres from the centre of the survey area, x east, y north):
  /mission/info           MissionInfo      the mission and how it stands (kept for late subscribers)
  /sensors/readings       SensorReading    every MD/GPR reading (kept for late subscribers)
  /uav/fix                NavSatFix        latest position
  /uav/pose               PoseStamped      latest position and heading in the survey frame
  /uav/path               Path             the track flown so far
  /uav/battery            BatteryState
  /landmine/detections    DetectionArray   the backend's adaptive detections, with their verification
  /landmine/markers       MarkerArray      area, readings and the backend's detections, for RViz
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import rclpy
import requests
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import BatteryState, NavSatFix
from uav_landmine_interfaces.msg import DetectionArray, MissionInfo, SensorReading
from visualization_msgs.msg import MarkerArray

from . import messages
from .backend_client import Backend, BackendError, credentials
from .core import FINISHED, SAMPLE_PERIOD_S, SurveyFrame
from .run import spin

READINGS_KEPT = 50_000  # readings kept for a subscriber that joins late (the demo has 3,293)
DETECTIONS_EVERY = 4  # polls between two reads of the backend's detections


def latched(depth: int = 1) -> QoSProfile:
    return QoSProfile(depth=depth, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)


@dataclass
class Followed:
    mission: dict
    frame: SurveyFrame
    last_reading_id: int = 0
    readings: int = 0
    last_t: float = -1.0
    complete: bool = False
    polls: int = 0
    info_key: tuple = ()
    path: Path = field(default_factory=Path)
    points: list = field(default_factory=list)  # (x, y, md) of the readings, for the markers


class MissionBridge(Node):
    def __init__(self) -> None:
        super().__init__("mission_bridge")
        self.declare_parameter("backend_url", "http://127.0.0.1:8000")
        self.declare_parameter("mission_id", 0)  # 0: the next mission that flies, then the one after it
        self.declare_parameter("poll_period_s", 0.5)
        self.declare_parameter("page_size", 2000)
        url = self.get_parameter("backend_url").value
        self._wanted = int(self.get_parameter("mission_id").value)
        self._period = float(self.get_parameter("poll_period_s").value)
        self._page = int(self.get_parameter("page_size").value)
        self._backend = Backend(url, *credentials())

        self._info = self.create_publisher(MissionInfo, "/mission/info", latched())
        self._readings = self.create_publisher(SensorReading, "/sensors/readings", latched(READINGS_KEPT))
        self._fix = self.create_publisher(NavSatFix, "/uav/fix", 10)
        self._pose = self.create_publisher(PoseStamped, "/uav/pose", 10)
        self._path = self.create_publisher(Path, "/uav/path", latched())
        self._battery = self.create_publisher(BatteryState, "/uav/battery", 10)
        self._detections = self.create_publisher(DetectionArray, "/landmine/detections", latched())
        self._markers = self.create_publisher(MarkerArray, "/landmine/markers", latched(10))

        self._followed: Followed | None = None
        self._waiting_logged = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="backend-poll", daemon=True)
        self._thread.start()
        which = f"mission {self._wanted}" if self._wanted else "the next mission that flies"
        self.get_logger().info(f"Following {which} on {url}")

    def stop(self) -> None:
        """Ends the polling (the thread is a daemon, so it never keeps the process alive)."""
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while rclpy.ok() and not self._stop.is_set():
            try:
                self._poll()
            except (BackendError, requests.RequestException) as exc:
                self.get_logger().warning(f"Backend: {exc}", throttle_duration_sec=10.0)
            self._stop.wait(self._period)

    def _choose(self) -> dict | None:
        if self._wanted:
            return self._backend.mission(self._wanted)
        followed = self._followed
        running = [m for m in self._backend.missions() if m["status"] == "running"]
        newer = [m for m in running if followed is None or m["id"] > followed.mission["id"]]
        return min(newer, key=lambda m: m["id"]) if newer else None

    def _poll(self) -> None:
        f = self._followed
        if f is None or (f.complete and not self._wanted):
            mission = self._choose()
            if mission is None:
                if not self._waiting_logged:
                    self.get_logger().info("Waiting for a mission to start in the dashboard")
                    self._waiting_logged = True
                if f is not None:
                    if f.polls % DETECTIONS_EVERY == 0:
                        self._publish_detections(f)  # verification may still change
                    f.polls += 1
                return
            if f is None or mission["id"] != f.mission["id"]:
                self._waiting_logged = False
                f = self._followed = Followed(mission, SurveyFrame.centred_on(mission["area"]))
                f.path.header = messages.header(self.get_clock().now().to_msg())
                area = messages.area_marker(mission, f.frame, f.path.header.stamp)
                self._markers.publish(MarkerArray(markers=[area]))
                self.get_logger().info(f"Mission {mission['id']} ({mission['name']}): {mission['status']}")
        elif f.complete:
            if f.polls % DETECTIONS_EVERY == 0:
                self._publish_detections(f)
            f.polls += 1
            return

        f.mission = self._backend.mission(f.mission["id"])
        ended = f.mission["status"] in FINISHED  # read before the readings, so none is stored after the last page
        stamp = self.get_clock().now().to_msg()
        caught_up = self._publish_readings(f, stamp)
        self._publish_telemetry(f, stamp)
        if f.polls % DETECTIONS_EVERY == 0 or ended:
            self._publish_detections(f)
        f.polls += 1
        if ended and caught_up:
            f.complete = True
            self.get_logger().info(f"Mission {f.mission['id']} {f.mission['status']}: {f.readings} readings published")
        self._publish_info(f)

    def _publish_readings(self, f: Followed, stamp) -> bool:
        """New readings, every page; True when the last page was not full."""
        while True:
            page = self._backend.readings(f.mission["id"], f.last_reading_id, self._page)
            for r in page:
                self._readings.publish(messages.sensor_reading(r, f.mission["id"], stamp))
                f.points.append((r["x_m"], r["y_m"], r["md"]))
            if page:
                f.last_reading_id = page[-1]["id"]
                f.readings += len(page)
                self._markers.publish(MarkerArray(markers=[messages.readings_marker(f.points, stamp)]))
            if len(page) < self._page:
                return True

    def _publish_telemetry(self, f: Followed, stamp) -> None:
        points = self._backend.telemetry(f.mission["id"], f.last_t, 5000)
        if not points:
            return
        f.last_t = points[-1]["t_s"]
        for t in points:
            f.path.poses.append(messages.pose(t, f.frame, stamp))
        latest = points[-1]
        self._fix.publish(messages.nav_sat_fix(latest, stamp))
        self._pose.publish(messages.pose(latest, f.frame, stamp))
        self._battery.publish(messages.battery(latest, stamp))
        f.path.header.stamp = stamp
        self._path.publish(f.path)

    def _publish_detections(self, f: Followed) -> None:
        stamp = self.get_clock().now().to_msg()
        found = [messages.backend_detection(d, f.frame) for d in self._backend.detections(f.mission["id"])]
        self._detections.publish(
            DetectionArray(
                header=messages.header(stamp), source="backend", mission_id=f.mission["id"], final=f.complete,
                detections=found,
            )
        )  # fmt: skip
        self._markers.publish(MarkerArray(markers=messages.detection_markers(found, "backend_detections", stamp)))

    def _publish_info(self, f: Followed) -> None:
        m = f.mission
        key = (m["status"], round(m["progress"], 3), f.readings, f.complete, m.get("sensor_collection"))
        if key != f.info_key:
            f.info_key = key
            self._info.publish(messages.mission_info(m, f.frame, SAMPLE_PERIOD_S, f.readings, f.complete))


def main(args=None) -> None:
    try:
        spin(MissionBridge, on_exit=lambda node: node.stop(), args=args)
    except BackendError as exc:
        print(f"mission_bridge: {exc}")
        raise SystemExit(2) from None

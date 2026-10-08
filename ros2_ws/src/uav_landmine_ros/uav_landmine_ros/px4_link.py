"""px4_link: reads PX4 directly, over uXRCE-DDS (PX4's own uxrce_dds_client and the Micro XRCE-DDS Agent), and
checks it against the backend.

It only reads: the backend still flies the mission over MAVLink and is the only one that commands PX4. This node
shows what PX4 itself says, so a difference between the two shows up (a lag, a wrong position, a landing the backend
has not seen yet).

  /px4/fix       NavSatFix     PX4's global position (vehicle_global_position)
  /px4/status    Px4Status     armed, on the ground, mode, failsafe, battery
  /px4/battery   BatteryState
  /diagnostics   "px4_link: PX4": how fresh PX4's messages are;
                 "px4_link: PX4 vs backend": metres between PX4's position and the backend's (MAVLink), and whether
                 both say the UAV is flying or down. Needs UAV_USERNAME and UAV_PASSWORD; without them it is skipped.
"""

from __future__ import annotations

import threading
import time

import rclpy
import requests
from diagnostic_msgs.msg import DiagnosticArray
from px4_msgs.msg import BatteryStatus, VehicleGlobalPosition, VehicleLandDetected, VehicleStatus
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import BatteryState, NavSatFix, NavSatStatus
from uav_landmine_interfaces.msg import Px4Status

from . import messages
from .backend_client import Backend, BackendError, credentials
from .bridge import described
from .px4_core import ARMING_STATE_ARMED, Fix, Track, compare, nav_state_name
from .run import spin

# What PX4 publishes with (its docs): best effort, kept for a subscriber that joins late.
PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST, depth=1,
)  # fmt: skip
STALE_S = 2.0  # PX4 publishes its position at up to 50 Hz: silent for this long, the link is down


class Px4Link(Node):
    def __init__(self) -> None:
        super().__init__("px4_link")
        self.declare_parameter("backend_url", "http://127.0.0.1:8000", described("The backend's address"))
        self.declare_parameter(
            "mission_id", 0, described("The backend mission to compare with; 0: the PX4 mission flying, or the last")
        )
        self.declare_parameter("poll_period_s", 1.0, described("Seconds between two reads of the backend"))
        self.declare_parameter("topic_prefix", "/fmu/out", described("Where PX4's messages are (its namespace)"))
        # PX4 v1.16 and later add the message's version to a topic whose message has changed (v1 here).
        self.declare_parameter("status_topic", "vehicle_status_v1", described("PX4's vehicle status topic"))
        self.declare_parameter("battery_topic", "battery_status_v1", described("PX4's battery topic"))
        p = {name: self.get_parameter(name).value for name in (
            "backend_url", "mission_id", "poll_period_s", "topic_prefix", "status_topic", "battery_topic")}  # fmt: skip
        prefix = p["topic_prefix"].rstrip("/")

        self._lock = threading.Lock()
        self._track = Track()
        self._position: VehicleGlobalPosition | None = None
        self._status: VehicleStatus | None = None
        self._land: VehicleLandDetected | None = None
        self._battery: BatteryStatus | None = None
        self._last_heard: float | None = None
        self._mission: dict | None = None
        self._backend_fix: dict | None = None
        self._backend_error = ""

        self.create_subscription(VehicleGlobalPosition, f"{prefix}/vehicle_global_position", self._on_position, PX4_QOS)
        self.create_subscription(VehicleStatus, f"{prefix}/{p['status_topic']}", self._on_status, PX4_QOS)
        self.create_subscription(VehicleLandDetected, f"{prefix}/vehicle_land_detected", self._on_land, PX4_QOS)
        self.create_subscription(BatteryStatus, f"{prefix}/{p['battery_topic']}", self._on_battery, PX4_QOS)
        self._fix_pub = self.create_publisher(NavSatFix, "/px4/fix", 10)
        self._status_pub = self.create_publisher(Px4Status, "/px4/status", 10)
        self._battery_pub = self.create_publisher(BatteryState, "/px4/battery", 10)
        self._diagnostics = self.create_publisher(DiagnosticArray, "/diagnostics", 10)
        self.create_timer(0.5, self._publish_status)
        self.create_timer(1.0, self._publish_diagnostics)

        self._wanted = int(p["mission_id"])
        self._period = float(p["poll_period_s"])
        self._stop = threading.Event()
        try:
            self._backend: Backend | None = Backend(p["backend_url"], *credentials())
        except BackendError as exc:
            self._backend, self._backend_error = None, str(exc)
            self.get_logger().warning(f"Not compared with the backend: {exc}")
        self._thread = threading.Thread(target=self._run, name="backend-poll", daemon=True)
        if self._backend is not None:
            self._thread.start()
        self.get_logger().info(f"Reading PX4 on {prefix}; comparing with {p['backend_url']}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    # PX4's messages.

    def _heard(self) -> None:
        self._last_heard = time.monotonic()

    def _on_position(self, msg: VehicleGlobalPosition) -> None:
        with self._lock:
            self._heard()
            self._position = msg
            if msg.lat_lon_valid:
                self._track.add(Fix(time.monotonic(), msg.lat, msg.lon, float(msg.alt)))
        if not msg.lat_lon_valid:
            return
        fix = NavSatFix(
            header=messages.header(self.get_clock().now().to_msg(), messages.UAV),
            status=NavSatStatus(status=NavSatStatus.STATUS_FIX, service=NavSatStatus.SERVICE_GPS),
            latitude=msg.lat, longitude=msg.lon, altitude=float(msg.alt),
            position_covariance_type=NavSatFix.COVARIANCE_TYPE_APPROXIMATED,
        )  # fmt: skip
        fix.position_covariance[0] = fix.position_covariance[4] = float(msg.eph) ** 2
        fix.position_covariance[8] = float(msg.epv) ** 2
        self._fix_pub.publish(fix)

    def _on_status(self, msg: VehicleStatus) -> None:
        with self._lock:
            self._heard()
            self._status = msg

    def _on_land(self, msg: VehicleLandDetected) -> None:
        with self._lock:
            self._heard()
            self._land = msg

    def _on_battery(self, msg: BatteryStatus) -> None:
        with self._lock:
            self._heard()
            self._battery = msg
        self._battery_pub.publish(
            BatteryState(
                header=messages.header(self.get_clock().now().to_msg(), messages.UAV),
                voltage=float(msg.voltage_v), percentage=float(msg.remaining), present=bool(msg.connected),
            )
        )  # fmt: skip

    def _publish_status(self) -> None:
        with self._lock:
            s, land, pos, bat = self._status, self._land, self._position, self._battery
        if s is None and land is None and pos is None:
            return
        out = Px4Status(header=messages.header(self.get_clock().now().to_msg(), messages.UAV))
        if s is not None:
            out.armed = s.arming_state == ARMING_STATE_ARMED
            out.nav_state, out.nav_state_name, out.failsafe = s.nav_state, nav_state_name(s.nav_state), s.failsafe
        if land is not None:
            out.landed, out.maybe_landed = land.landed, land.maybe_landed
        out.battery_remaining = float(bat.remaining) if bat is not None else -1.0
        if pos is not None:
            out.position_valid = bool(pos.lat_lon_valid)
            out.latitude, out.longitude, out.altitude_amsl_m = pos.lat, pos.lon, float(pos.alt)
        self._status_pub.publish(out)

    # The backend.

    def _run(self) -> None:
        last_t, mission_id = -1.0, None
        while rclpy.ok() and not self._stop.is_set():
            try:
                mission = self._choose()
                if mission is not None and mission["id"] != mission_id:
                    mission_id, last_t = mission["id"], -1.0
                    with self._lock:
                        self._backend_fix = None
                    self.get_logger().info(f"Comparing with mission {mission_id} ({mission['name']})")
                if mission is not None:
                    while True:  # to the backend's latest position
                        points = self._backend.telemetry(mission_id, last_t, 5000)
                        if not points:
                            break
                        last_t = points[-1]["t_s"]
                        with self._lock:
                            self._backend_fix = points[-1]
                        if len(points) < 5000:
                            break
                with self._lock:
                    self._mission, self._backend_error = mission, ""
            except (BackendError, requests.RequestException) as exc:
                with self._lock:
                    self._backend_error = str(exc)
                self.get_logger().warning(f"Backend: {exc}", throttle_duration_sec=10.0)
            except Exception:
                if not rclpy.ok() or self._stop.is_set():
                    return  # ROS shut down (Ctrl+C) meanwhile
                raise
            self._stop.wait(self._period)

    def _choose(self) -> dict | None:
        """The mission asked for; otherwise the PX4 mission running, else the PX4 mission started last."""
        if self._wanted:
            return self._backend.mission(self._wanted)
        px4 = [m for m in self._backend.missions() if m.get("uav_source") == "px4" and m.get("status") != "planned"]
        running = [m for m in px4 if m["status"] == "running"]
        chosen = max(running or px4, key=lambda m: (m.get("started_at") or "", m["id"]), default=None)
        return None if chosen is None else self._backend.mission(chosen["id"])

    def _publish_diagnostics(self) -> None:
        with self._lock:
            heard, land, error = self._last_heard, self._land, self._backend_error
            result = compare(self._track, None if land is None else bool(land.landed), self._mission, self._backend_fix)
        age = None if heard is None else time.monotonic() - heard
        link = messages.diagnostic(
            "px4_link: PX4",
            age is not None and age < STALE_S,
            "PX4 heard over uXRCE-DDS" if age is not None and age < STALE_S else "Nothing from PX4 (agent? PX4?)",
            {"last_message_age_s": "never" if age is None else round(age, 1)},
        )
        if self._backend is None:
            vs = messages.diagnostic("px4_link: PX4 vs backend", False, f"Not compared: {error}", {}, warn=True)
        elif error:
            vs = messages.diagnostic("px4_link: PX4 vs backend", False, f"Backend: {error}", result.values)
        else:
            vs = messages.diagnostic("px4_link: PX4 vs backend", result.ok, result.message, result.values, result.warn)
        msg = DiagnosticArray(status=[link, vs])
        msg.header.stamp = self.get_clock().now().to_msg()
        self._diagnostics.publish(msg)


def main(args=None) -> None:
    spin(Px4Link, on_exit=lambda node: node.stop(), args=args, threads=2)

"""compare_with_backend: waits for the detector node's final potential detections of a mission and compares them
with the ones the backend stored for it (category, number of readings, score to 3 places, position): read from the
backend, or (against:=recording) from the backend's final /landmine/detections in a recording being replayed.

Exit code 0 when they are the same, 1 when they differ, 2 when nothing final came in time.
"""

from __future__ import annotations

import signal

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from uav_landmine_interfaces.msg import DetectionArray

from .backend_client import Backend, BackendError, credentials
from .bridge import latched
from .core import rounded


class Compare(Node):
    def __init__(self) -> None:
        super().__init__("compare_with_backend")
        self.declare_parameter("backend_url", "http://127.0.0.1:8000")
        self.declare_parameter("mission_id", 0)  # 0: the first mission whose final result comes
        self.declare_parameter("timeout_s", 900.0)
        self.declare_parameter("against", "backend")  # or "recording": /landmine/detections, no backend needed
        self._mission = int(self.get_parameter("mission_id").value)
        self._recorded = self.get_parameter("against").value == "recording"
        self._backend = None if self._recorded else Backend(self.get_parameter("backend_url").value, *credentials())
        self._stored: dict[int, list[tuple]] = {}  # mission -> the backend's final detections, from the recording
        self._ours: DetectionArray | None = None
        self.result: int | None = None
        self.create_subscription(DetectionArray, "/landmine/candidates", self._on_candidates, latched())
        if self._recorded:
            self.create_subscription(DetectionArray, "/landmine/detections", self._on_stored, latched())
        self.create_timer(float(self.get_parameter("timeout_s").value), self._timeout)

    def _on_stored(self, msg: DetectionArray) -> None:
        if msg.final:
            self._stored[msg.mission_id] = [
                rounded(d.category, d.confidence, d.n_hits, d.latitude, d.longitude) for d in msg.detections
            ]
            if self._ours is not None:
                self._on_candidates(self._ours)

    def _on_candidates(self, msg: DetectionArray) -> None:
        if not msg.final or (self._mission and msg.mission_id != self._mission) or self.result is not None:
            return
        if self._recorded:
            if msg.mission_id not in self._stored:
                self._ours = msg  # the backend's final detections come later in the recording
                return
            theirs = sorted(self._stored[msg.mission_id])
        else:
            stored = self._backend.detections(msg.mission_id)
            theirs = sorted(rounded(d["category"], d["confidence"], d["n_hits"], d["lat"], d["lon"]) for d in stored)
        ours = sorted(rounded(d.category, d.confidence, d.n_hits, d.latitude, d.longitude) for d in msg.detections)
        log = self.get_logger()
        if ours == theirs:
            log.info(f"Mission {msg.mission_id}: the detector node and the backend agree on all {len(ours)} "
                     "potential detections")
            self.result = 0
            return
        log.error(f"Mission {msg.mission_id}: {len(ours)} from the detector node, {len(theirs)} in the backend")
        for d in sorted(set(ours) - set(theirs)):
            log.error(f"  only in ROS:     {d}")
        for d in sorted(set(theirs) - set(ours)):
            log.error(f"  only in backend: {d}")
        self.result = 1

    def _timeout(self) -> None:
        if self.result is None:
            self.get_logger().error("No final result from the detector node in time")
            self.result = 2


def main(args=None) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # as run.spin: rclpy's handler stops it, a second Ctrl+C is ignored
    rclpy.init(args=args)
    node = None
    try:
        node = Compare()
        while rclpy.ok() and node.result is None:
            rclpy.spin_once(node, timeout_sec=0.5)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except BackendError as exc:
        print(f"compare_with_backend: {exc}")
    finally:
        try:
            rclpy.try_shutdown()
        except KeyboardInterrupt:
            pass
    raise SystemExit(2 if node is None or node.result is None else node.result)

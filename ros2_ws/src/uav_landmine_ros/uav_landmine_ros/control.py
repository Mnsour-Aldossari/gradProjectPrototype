"""mission_control: start and command missions from ROS 2, through the backend.

  /mission/start    StartMission    start a planned mission, or the demo scenario (mission_id 0)
  /mission/control  ControlMission  pause, resume, return or land (mission_id 0: the one flying)
  /mission/fly      FlySurvey       start a mission and follow it to its end, with feedback; cancelling lands the UAV

Every command goes to the backend's REST API with a supervisor's account (UAV_CONTROL_USERNAME and
UAV_CONTROL_PASSWORD); the backend refuses the field operator's. The backend then flies the mission as when the
dashboard's buttons are used, so both always show the same mission.
"""

from __future__ import annotations

import time

import requests
from rclpy.action import ActionServer, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from uav_landmine_interfaces.action import FlySurvey
from uav_landmine_interfaces.srv import ControlMission, StartMission

from .backend_client import Backend, BackendError, credentials
from .bridge import described
from .control_core import Answer, ControlCore
from .run import spin


class MissionControl(Node):
    def __init__(self) -> None:
        super().__init__("mission_control")
        self.declare_parameter("backend_url", "http://127.0.0.1:8000", described("The backend's address"))
        self.declare_parameter("feedback_period_s", 1.0, described("Seconds between two feedbacks of /mission/fly"))
        url = self.get_parameter("backend_url").value
        self._period = float(self.get_parameter("feedback_period_s").value)
        try:
            self._core: ControlCore | None = ControlCore(Backend(url, *credentials("UAV_CONTROL")))
            self._missing = ""
        except BackendError as exc:
            self._core, self._missing = None, str(exc)
            self.get_logger().warning(f"Commands will be refused: {exc}")
        group = ReentrantCallbackGroup()  # a long /mission/fly must not hold up the services
        self.create_service(StartMission, "/mission/start", self._start, callback_group=group)
        self.create_service(ControlMission, "/mission/control", self._control, callback_group=group)
        self._fly_server = ActionServer(
            self, FlySurvey, "/mission/fly", execute_callback=self._fly,
            cancel_callback=lambda _goal: CancelResponse.ACCEPT, callback_group=group,
        )  # fmt: skip
        self.get_logger().info(f"Commands go to {url}: /mission/start, /mission/control, /mission/fly")

    def _start(self, request: StartMission.Request, response: StartMission.Response) -> StartMission.Response:
        r = request
        answer = self._ask(lambda core: core.start(r.mission_id, r.uav_source, r.speed_factor, r.gazebo), r.mission_id)
        response.accepted, response.mission_id, response.message = answer.accepted, answer.mission_id, answer.message
        return response

    def _control(self, request: ControlMission.Request, response: ControlMission.Response) -> ControlMission.Response:
        answer = self._ask(lambda core: core.control(request.mission_id, request.action), request.mission_id)
        response.accepted, response.mission_id = answer.accepted, answer.mission_id
        response.phase, response.message = answer.phase, answer.message
        return response

    def _ask(self, call, mission_id: int) -> Answer:
        if self._core is None:
            return Answer(False, mission_id, self._missing)
        try:
            answer = call(self._core)
        except (BackendError, requests.RequestException) as exc:
            answer = Answer(False, mission_id, f"Backend: {exc}")
        log = self.get_logger().info if answer.accepted else self.get_logger().warning
        log(answer.message)
        return answer

    def _fly(self, goal):
        g = goal.request
        result = FlySurvey.Result()
        answer = self._ask(lambda core: core.start(g.mission_id, g.uav_source, g.speed_factor, g.gazebo), g.mission_id)
        if not answer.accepted:
            result.mission_id, result.status, result.message = g.mission_id, "refused", answer.message
            result.sensor_coverage = -1.0
            goal.abort()
            return result
        mission_id, cancel_sent = answer.mission_id, False
        while True:
            try:
                p = self._core.progress(mission_id)
            except (BackendError, requests.RequestException) as exc:
                self.get_logger().warning(f"Backend: {exc}", throttle_duration_sec=10.0)
                time.sleep(self._period)
                continue
            goal.publish_feedback(
                FlySurvey.Feedback(
                    mission_id=mission_id, status=p.status, phase=p.phase, progress=p.progress, readings=p.readings,
                    high_priority=p.high, needs_verification=p.suspect,
                )
            )  # fmt: skip
            if goal.is_cancel_requested and not cancel_sent:
                self._ask(lambda core: core.control(mission_id, g.cancel_action or "land"), mission_id)
                cancel_sent = True  # the mission still ends as the backend says: stopped once the UAV is down
            if p.finished:
                break
            time.sleep(self._period)
        result.mission_id, result.status, result.message = mission_id, p.status, p.error
        result.sensor_collection, result.sensor_coverage = p.sensor_collection, p.sensor_coverage
        result.readings = p.readings
        result.high_priority, result.needs_verification, result.likely_clutter = p.high, p.suspect, p.clutter
        if cancel_sent:
            goal.canceled()
        else:
            goal.succeed()
        return result


def main(args=None) -> None:
    spin(MissionControl, args=args, threads=4)

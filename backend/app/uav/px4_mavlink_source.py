"""TelemetrySource backed by PX4 over MAVLink, through MAVSDK: PX4 SITL + Gazebo, or a real vehicle.

PX4 flies the survey path; the frames carry PX4's own position, height, speed, heading, battery and mission
progress. MD and GPR readings are not MAVLink data, so the project's sensor model reads the scenario's buried
objects at PX4's position (px4_plan.py), as a payload computer would add its own stream on a real UAV.

MAVSDK is optional (requirements-px4.txt) and imported only when a mission flies with PX4, so the backend runs
without it.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections.abc import AsyncIterator

from app.simulation import SimulationConfig, build_simulation

from .px4_plan import (
    ACCEPTANCE_RADIUS_M,
    PathProgress,
    Px4State,
    Waypoint,
    WaypointTracker,
    build_frame,
    home_check,
    survey_waypoints,
)
from .source import TelemetryFrame

DISCOVERY_TIMEOUT_S = 10.0  # how long to listen for PX4's heartbeat
READY_TIMEOUT_S = 60.0  # GPS fix and home position, a few seconds after PX4 SITL starts
ARMABLE_TIMEOUT_S = 15.0  # after switching to Hold
LINK_TIMEOUT_S = 5.0  # no position from PX4 for this long ends the run
FRAME_PERIOD_S = 0.2  # the simulator's dt_s, which the detector expects between readings
RATE_HZ = 1 / FRAME_PERIOD_S


class Px4Unavailable(Exception):
    """PX4 cannot fly this mission now. The message says why and what to do."""


def mavsdk_installed() -> bool:
    try:
        import mavsdk.asyncio  # noqa: F401
    except (ImportError, OSError):  # OSError: the bundled MAVSDK library could not be loaded
        return False
    return True


# One MAVSDK instance per connection URL for the backend's lifetime: it keeps listening between missions.
_links: dict[str, object] = {}
# Two starts at once must not both open the port. A lock belongs to one event loop, so one per loop (tests use several).
_locks: dict[int, asyncio.Lock] = {}


async def _connect(url: str):
    from mavsdk.asyncio import ComponentType, Configuration, Mavsdk, MavsdkConnectionError

    async with _locks.setdefault(id(asyncio.get_running_loop()), asyncio.Lock()):
        if url not in _links:
            mavsdk = Mavsdk(Configuration.create_with_component_type(ComponentType.GROUND_STATION))
            try:
                await mavsdk.add_any_connection(url)
            except MavsdkConnectionError as e:
                mavsdk.destroy()
                raise Px4Unavailable(f"Cannot listen for PX4 on {url}: {e}") from e
            _links[url] = mavsdk
        mavsdk = _links[url]
    system = await mavsdk.first_autopilot(timeout_s=DISCOVERY_TIMEOUT_S)
    # A system seen before stays in MAVSDK's list after PX4 stops, so check that it is still there.
    if system is None or not await system.is_connected():
        raise Px4Unavailable(
            f"No PX4 answered on {url} within {DISCOVERY_TIMEOUT_S:.0f} s. Start PX4 SITL (README, 'PX4 SITL + Gazebo') "
            "and try again."
        )
    return system


def _mission_item(w: Waypoint):
    from mavsdk.plugins.mission import MissionItem

    nan = float("nan")
    return MissionItem(
        latitude_deg=w.lat,
        longitude_deg=w.lon,
        relative_altitude_m=w.relative_alt_m,
        speed_m_s=w.speed_m_s,
        is_fly_through=False,  # stop at each lane end, as the survey lines are flown straight
        gimbal_pitch_deg=nan,
        gimbal_yaw_deg=nan,
        camera_action=MissionItem.CameraAction.NONE,
        loiter_time_s=nan,
        camera_photo_interval_s=nan,
        acceptance_radius_m=ACCEPTANCE_RADIUS_M,
        yaw_deg=nan,
        camera_photo_distance_m=nan,
        vehicle_action=MissionItem.VehicleAction.NONE,
    )


def _number(value: float | None, fallback: float) -> float:
    return fallback if value is None or math.isnan(value) else value


class Px4MavlinkSource:
    """Flies one mission on PX4. Call connect() first: it fails with Px4Unavailable before anything changes."""

    def __init__(self, config: SimulationConfig, url: str = "udpin://0.0.0.0:14540") -> None:
        self.url = url
        self._sim = build_simulation(config)
        self._waypoints = survey_waypoints(self._sim)
        self._system = None

    async def connect(self) -> None:
        """Find PX4, wait until it can fly, check the area is in reach and upload the survey."""
        if not mavsdk_installed():
            raise Px4Unavailable("PX4 support is not installed on the server: pip install -r requirements-px4.txt")
        from mavsdk.asyncio.plugins.action import ActionAsync, ActionError
        from mavsdk.asyncio.plugins.mission import MissionAsync, MissionError, MissionPlan
        from mavsdk.asyncio.plugins.telemetry import TelemetryAsync

        system = await _connect(self.url)
        telemetry = TelemetryAsync(system)
        try:
            await asyncio.wait_for(
                self._until(telemetry, lambda h: h.is_global_position_ok and h.is_home_position_ok), READY_TIMEOUT_S
            )
        except TimeoutError as e:
            raise Px4Unavailable(
                "PX4 has no GPS fix or home position yet. Wait until it has started, then try again."
            ) from e
        home = await telemetry.home()
        reason = home_check((home.latitude_deg, home.longitude_deg), self._waypoints)
        if reason:
            raise Px4Unavailable(reason)
        mission = MissionAsync(system)
        try:
            await mission.set_return_to_launch_after_mission(True)
            await mission.upload_mission(MissionPlan([_mission_item(w) for w in self._waypoints]))
        except MissionError as e:
            raise Px4Unavailable(f"PX4 did not accept the survey: {e}") from e
        # After a flight PX4 stays in Return (or Land) mode, where it refuses to arm; Hold mode can arm.
        if (await telemetry.health()).is_armable is False:
            with contextlib.suppress(ActionError):
                await ActionAsync(system).hold()
            try:
                await asyncio.wait_for(self._until(telemetry, lambda h: h.is_armable is not False), ARMABLE_TIMEOUT_S)
            except TimeoutError as e:
                raise Px4Unavailable(
                    "PX4 is not ready to arm: one of its preflight checks fails (see the PX4 console). Try again "
                    "once it is fixed."
                ) from e
        self._system = system

    @staticmethod
    async def _until(telemetry, ok) -> None:
        """Wait for a health report that passes ok()."""
        async with contextlib.aclosing(telemetry.subscribe_health()) as health:
            async for h in health:
                if ok(h):
                    return

    async def frames(self) -> AsyncIterator[TelemetryFrame]:
        if self._system is None:
            raise RuntimeError("connect() must succeed before frames()")
        from mavsdk.asyncio.plugins.action import ActionAsync, ActionError
        from mavsdk.asyncio.plugins.mission import MissionAsync, MissionError
        from mavsdk.asyncio.plugins.telemetry import TelemetryAsync

        telemetry, mission, action = TelemetryAsync(self._system), MissionAsync(self._system), ActionAsync(self._system)
        latest: dict[str, object] = {}
        position_at = [0.0]

        async def follow(name: str, stream) -> None:
            async with contextlib.aclosing(stream) as values:
                async for value in values:
                    latest[name] = value
                    if name == "position":
                        position_at[0] = time.monotonic()

        streams = {
            "position": telemetry.subscribe_position(),
            "velocity": telemetry.subscribe_velocity_ned(),
            "heading": telemetry.subscribe_heading(),
            "battery": telemetry.subscribe_battery(),
            "armed": telemetry.subscribe_armed(),
        }
        tasks = [asyncio.create_task(follow(name, stream)) for name, stream in streams.items()]
        for set_rate in (telemetry.set_rate_position, telemetry.set_rate_velocity_ned, telemetry.set_rate_battery):
            with contextlib.suppress(Exception):  # PX4 keeps its own rate if it refuses
                await set_rate(RATE_HZ)

        finished = False
        try:
            try:
                await action.arm()
                await mission.start_mission()
            except (ActionError, MissionError) as e:
                raise RuntimeError(f"PX4 did not start the survey: {e}") from e

            progress = PathProgress(self._sim.plan)
            tracker = WaypointTracker(self._sim.plan)
            loop = asyncio.get_running_loop()
            start = loop.time()
            was_armed = False
            for i in range(1, 2**31):
                await asyncio.sleep(max(0.0, start + i * FRAME_PERIOD_S - loop.time()))
                pos = latest.get("position")
                if pos is None or time.monotonic() - position_at[0] > LINK_TIMEOUT_S:
                    if pos is not None or loop.time() - start > LINK_TIMEOUT_S:
                        raise RuntimeError(f"Lost the link to PX4: no position for {LINK_TIMEOUT_S:.0f} s")
                    continue
                vel, hdg, bat = (latest.get(k) for k in ("velocity", "heading", "battery"))
                v_n = _number(getattr(vel, "north_m_s", None), 0.0)
                v_e = _number(getattr(vel, "east_m_s", None), 0.0)
                state = Px4State(
                    lat_deg=pos.latitude_deg,
                    lon_deg=pos.longitude_deg,
                    absolute_alt_m=pos.absolute_altitude_m,
                    relative_alt_m=pos.relative_altitude_m,
                    v_north_m_s=v_n,
                    v_east_m_s=v_e,
                    v_down_m_s=_number(getattr(vel, "down_m_s", None), 0.0),
                    heading_deg=_number(getattr(hdg, "heading_deg", None), math.degrees(math.atan2(v_e, v_n)) % 360),
                    battery_pct=_number(getattr(bat, "remaining_percent", None), 100.0),
                    current=tracker.update(*self._sim.frame.to_xy(pos.latitude_deg, pos.longitude_deg)),
                    total=tracker.total,
                )
                yield build_frame(state, loop.time() - start, self._sim, progress)
                if state.current >= state.total:
                    finished = True  # PX4 flies home on its own (return to launch after the mission)
                    return
                armed = latest.get("armed")
                was_armed = was_armed or armed is True
                if was_armed and armed is False:
                    raise RuntimeError("PX4 disarmed before the survey was finished")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if not finished:
                with contextlib.suppress(Exception):  # cancelled or failed: bring the vehicle back
                    await action.return_to_launch()

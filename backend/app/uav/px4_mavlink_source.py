"""PX4 / MAVLink telemetry source - FUTURE PHASE, NOT IMPLEMENTED.

This stub documents where a real (or PX4 SITL + Gazebo) UAV plugs in. The
prototype uses `SimulatedSource`; nothing in this file has been run or tested.

Planned design:
* Connect with MAVSDK-Python, e.g. `System().connect("udp://:14540")` for PX4 SITL.
* Subscribe to `telemetry.position()`, `telemetry.velocity_ned()`,
  `telemetry.heading()`, `telemetry.battery()` and `mission.mission_progress()`,
  and assemble them into `TelemetryFrame`s (GLOBAL_POSITION_INT,
  BATTERY_STATUS, MISSION_CURRENT fields).
* GPR / metal-detector samples are not MAVLink messages; they would arrive
  from the payload computer as a separate stream (optionally via ROS 2) and
  be time-aligned with the position stream before being attached as
  `SensorSample`.

Because the rest of the system only depends on the `TelemetrySource`
protocol, switching sources does not change the backend, detection engine,
database or user interfaces.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from .source import TelemetryFrame


class Px4MavlinkSource:
    def __init__(self, connection_url: str = "udp://:14540") -> None:
        self.connection_url = connection_url

    def frames(self) -> AsyncIterator[TelemetryFrame]:
        raise NotImplementedError(
            "PX4/MAVLink integration is a documented future phase; the prototype uses SimulatedSource."
        )

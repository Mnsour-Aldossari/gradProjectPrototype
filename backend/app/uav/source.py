"""The boundary between the UAV (real or simulated) and the rest of the system.

Everything downstream (mission runner, storage, detection) consumes
`TelemetryFrame`s from a `TelemetrySource` and does not know whether they come
from the built-in simulator or from PX4 over MAVLink (px4_mavlink_source.py).

Field names, units and scaling of the flight messages follow the MAVLink
common message set so a MAVLink adapter can fill them without conversion:
https://mavlink.io/en/messages/common.html
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .control import FlightControl


@dataclass(frozen=True)
class GlobalPositionInt:
    """MAVLink GLOBAL_POSITION_INT (#33)."""

    time_boot_ms: int
    lat: int  # degE7
    lon: int  # degE7
    alt: int  # mm above mean sea level
    relative_alt: int  # mm above ground (home)
    vx: int  # cm/s, north
    vy: int  # cm/s, east
    vz: int  # cm/s, down
    hdg: int  # cdeg, 0..35999


@dataclass(frozen=True)
class BatteryStatus:
    """Subset of MAVLink BATTERY_STATUS (#147)."""

    battery_remaining: int  # %


@dataclass(frozen=True)
class MissionCurrent:
    """Subset of MAVLink MISSION_CURRENT (#42)."""

    seq: int  # index of the waypoint being flown to
    total: int  # number of waypoints in the mission


@dataclass(frozen=True)
class SensorSample:
    """Project-defined payload sample. NOT a standard MAVLink message.

    GPR and metal-detector data are not part of the MAVLink common set; on a
    real UAV they would come from the payload computer as a separate stream.
    """

    md: float  # metal-detector response (normalised units)
    gpr_amp: float  # GPR reflection amplitude (normalised units)
    gpr_twt_ns: float  # two-way travel time of the strongest reflector


@dataclass(frozen=True)
class VehicleStatus:
    """What the vehicle says about itself, for confirming a landing (landing.py). From MAVLink HEARTBEAT (#0), the
    armed flag of base_mode, and EXTENDED_SYS_STATE (#245) landed_state; the failsafe and the age are project-defined
    (PX4 reports a failsafe in its status messages)."""

    armed: bool
    landed_state: int  # MAV_LANDED_STATE: 0 undefined, 1 on ground, 2 in air, 3 taking off, 4 landing
    failsafe: str | None = None  # what the vehicle said when a failsafe started; None: no failsafe
    age_s: float = 0.0  # how old the oldest of these values was when the frame was made


MAV_LANDED_STATE_ON_GROUND = 1
MAV_LANDED_STATE_IN_AIR = 2


@dataclass(frozen=True)
class TelemetryFrame:
    position: GlobalPositionInt
    battery: BatteryStatus
    mission: MissionCurrent
    sensor: SensorSample | None
    progress: float  # fraction of the survey path completed, 0..1
    status: VehicleStatus | None = None  # None: the source does not report it (the landing is then not confirmed)


class TelemetrySource(Protocol):
    # Set by the mission runner before frames(): the supervisor's pause, resume, return home and land commands.
    control: FlightControl | None

    def frames(self) -> AsyncIterator[TelemetryFrame]:
        """Yield frames until the survey ends."""
        ...

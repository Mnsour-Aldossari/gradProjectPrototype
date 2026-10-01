"""The boundary between the UAV (real or simulated) and the rest of the system.

Everything downstream (mission runner, storage, detection) consumes
`TelemetryFrame`s from a `TelemetrySource` and does not know whether they come
from the built-in simulator or, in a future phase, from PX4 over MAVLink.

Field names, units and scaling of the flight messages follow the MAVLink
common message set so a MAVLink adapter can fill them without conversion:
https://mavlink.io/en/messages/common.html
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


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
class TelemetryFrame:
    position: GlobalPositionInt
    battery: BatteryStatus
    mission: MissionCurrent
    sensor: SensorSample | None
    progress: float  # fraction of the survey path completed, 0..1


class TelemetrySource(Protocol):
    def frames(self) -> AsyncIterator[TelemetryFrame]:
        """Yield frames until the survey ends."""
        ...

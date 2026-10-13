"""Whether the UAV is safely on the ground when a flight ends.

A mission is only completed (or stopped, after Return Home or Land) once the last telemetry shows the UAV disarmed,
on the ground, recent and without a failsafe. Otherwise it fails with the reason, whatever the source: PX4 reports
these values through MAVSDK, the simulator reports its own.
"""

from __future__ import annotations

import math

from .source import MAV_LANDED_STATE_ON_GROUND, TelemetryFrame

GROUND_MARGIN_M = 0.35  # height above the takeoff ground still taken as on the ground
FRESH_S = 2.0  # older telemetry cannot confirm anything


def landing_problems(last: TelemetryFrame | None, age_s: float) -> list[str]:
    """Why the last frame does not confirm a landing; empty when it does. age_s: seconds since the frame arrived."""
    if last is None:
        return ["no telemetry from the UAV"]
    status = last.status
    if status is None:
        return ["the UAV did not report whether it is armed or on the ground"]
    problems = []
    age = status.age_s + age_s
    if math.isinf(age):
        problems.append("no telemetry on whether it is armed and on the ground")
    elif age >= FRESH_S:
        problems.append(f"the last telemetry is {age:.1f} s old")
    if status.armed:
        problems.append("still armed")
    if status.landed_state != MAV_LANDED_STATE_ON_GROUND:
        problems.append("not reported on the ground")
    height = last.position.relative_alt / 1000
    if abs(height) > GROUND_MARGIN_M:
        problems.append(f"{height:.2f} m above the ground")
    if status.failsafe:
        problems.append(f"failsafe: {status.failsafe}")
    return problems

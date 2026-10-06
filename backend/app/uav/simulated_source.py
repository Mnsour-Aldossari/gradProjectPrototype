"""TelemetrySource backed by the built-in simulator (no flight hardware)."""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Iterator

from app.simulation import Simulation, SimulationConfig, build_simulation
from app.simulation.flight import FlightSample
from app.simulation.sensors import SensorSample as SimSensorSample
from app.simulation.world import FLIGHT_ENDURANCE_S

from .control import FlightControl
from .source import BatteryStatus, GlobalPositionInt, MissionCurrent, SensorSample, TelemetryFrame

DESCENT_MPS = 0.5  # landing at the end of a return home or a land command


def to_frame(sim: Simulation, fs: FlightSample, ss: SimSensorSample | None) -> TelemetryFrame:
    lat, lon = sim.frame.to_latlon(fs.x, fs.y)
    return TelemetryFrame(
        position=GlobalPositionInt(
            time_boot_ms=round(fs.t_s * 1000),
            lat=round(lat * 1e7),
            lon=round(lon * 1e7),
            alt=round((sim.config.ground_elevation_m + fs.alt_m) * 1000),
            relative_alt=round(fs.alt_m * 1000),
            vx=round(fs.v_north * 100),
            vy=round(fs.v_east * 100),
            vz=0,
            hdg=round(fs.heading_deg * 100) % 36000,
        ),
        battery=BatteryStatus(battery_remaining=round(fs.battery_pct)),
        mission=MissionCurrent(seq=fs.waypoint_index, total=len(sim.plan.waypoints_xy)),
        sensor=None if ss is None else SensorSample(md=ss.md, gpr_amp=ss.gpr_amp, gpr_twt_ns=ss.gpr_twt_ns),
        progress=fs.progress,
    )


def fly_down(sim: Simulation, last: FlightSample, home: bool) -> Iterator[FlightSample]:
    """After a return-home or land command: straight to the start of the path if home, then straight down. The
    survey progress stays where it was stopped."""
    cfg = sim.config
    dt, drain = cfg.dt_s, 100.0 / FLIGHT_ENDURANCE_S
    x, y, alt, t, battery = last.x, last.y, last.alt_m, last.t_s, last.battery_pct
    heading = last.heading_deg

    def sample(v_east: float = 0.0, v_north: float = 0.0) -> FlightSample:
        return FlightSample(t, x, y, alt, v_east, v_north, heading, battery, last.waypoint_index, last.progress)

    tx, ty = sim.plan.waypoints_xy[0] if home else (x, y)
    step = cfg.speed_mps * dt
    while (d := math.dist((x, y), (tx, ty))) > 1e-9:
        v_e, v_n = (tx - x) / d * cfg.speed_mps, (ty - y) / d * cfg.speed_mps
        heading = math.degrees(math.atan2(v_e, v_n)) % 360
        k = min(1.0, step / d)
        x, y = x + (tx - x) * k, y + (ty - y) * k
        t, battery = t + dt, max(0.0, battery - drain * dt)
        yield sample(v_e, v_n)
    while alt > 0:
        alt = max(0.0, alt - DESCENT_MPS * dt)
        t, battery = t + dt, max(0.0, battery - drain * dt)
        yield sample()


class SimulatedSource:
    """Plays a simulated survey as a telemetry stream.

    speed_factor=1 runs in real time, 10 runs ten times faster, and 0 yields
    frames as fast as possible (used by tests and offline evaluation).
    The supervisor's commands (control) pause it, or end the survey with a
    flight home or a landing.
    """

    def __init__(self, config: SimulationConfig, speed_factor: float = 1.0) -> None:
        if speed_factor < 0:
            raise ValueError("speed_factor must be >= 0")
        self._config = config
        self._speed_factor = speed_factor
        self.control: FlightControl | None = None

    async def frames(self) -> AsyncIterator[TelemetryFrame]:
        sim = build_simulation(self._config)
        control = self.control
        period = self._config.dt_s / self._speed_factor if self._speed_factor > 0 else 0.0
        loop = asyncio.get_running_loop()
        start = loop.time()
        i = 0
        last: FlightSample | None = None

        async def pace() -> None:
            nonlocal i
            i += 1
            if period:
                await asyncio.sleep(max(0.0, start + i * period - loop.time()))
            elif i % 100 == 0:
                await asyncio.sleep(0)  # let other tasks run

        for fs, ss in sim.samples():
            if control is not None and control.phase == "paused":
                # Hovering in place: no frames, and the flight clock stops with it.
                await control.wait_while_paused()
                start = loop.time() - i * period
            if control is not None and control.stop_reason is not None:
                break
            yield to_frame(sim, fs, ss)
            last = fs
            await pace()
        if control is None or control.stop_reason is None or last is None:
            return
        for fs in fly_down(sim, last, home=control.phase == "returning"):
            yield to_frame(sim, fs, None)
            await pace()

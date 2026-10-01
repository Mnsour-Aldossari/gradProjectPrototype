"""TelemetrySource backed by the built-in simulator (no flight hardware)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.simulation import Simulation, SimulationConfig, build_simulation
from app.simulation.flight import FlightSample
from app.simulation.sensors import SensorSample as SimSensorSample

from .source import BatteryStatus, GlobalPositionInt, MissionCurrent, SensorSample, TelemetryFrame


def to_frame(sim: Simulation, fs: FlightSample, ss: SimSensorSample) -> TelemetryFrame:
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
        sensor=SensorSample(md=ss.md, gpr_amp=ss.gpr_amp, gpr_twt_ns=ss.gpr_twt_ns),
        progress=fs.progress,
    )


class SimulatedSource:
    """Plays a simulated survey as a telemetry stream.

    speed_factor=1 runs in real time, 10 runs ten times faster, and 0 yields
    frames as fast as possible (used by tests and offline evaluation).
    """

    def __init__(self, config: SimulationConfig, speed_factor: float = 1.0) -> None:
        if speed_factor < 0:
            raise ValueError("speed_factor must be >= 0")
        self._config = config
        self._speed_factor = speed_factor

    async def frames(self) -> AsyncIterator[TelemetryFrame]:
        sim = build_simulation(self._config)
        period = self._config.dt_s / self._speed_factor if self._speed_factor > 0 else 0.0
        loop = asyncio.get_running_loop()
        start = loop.time()
        for i, (fs, ss) in enumerate(sim.samples()):
            yield to_frame(sim, fs, ss)
            if period:
                await asyncio.sleep(max(0.0, start + (i + 1) * period - loop.time()))
            elif i % 100 == 0:
                await asyncio.sleep(0)  # let other tasks run

"""Assembles a complete simulated survey: area, path, scenario and sensors."""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from .flight import FlightSample, fly, path_length, survey_lanes
from .geo import XY, LatLon, LocalFrame, bounding_box
from .scenario import Scenario, generate_scenario
from .sensors import SensorModel, SensorSample

# A 60 m x 40 m test field in open ground near Al-Kharj (Prince Sattam Bin Abdulaziz University).
DEMO_AREA: tuple[LatLon, ...] = (
    (24.13968, 47.26170),
    (24.13968, 47.26230),
    (24.13932, 47.26230),
    (24.13932, 47.26170),
)

GROUND_ELEVATION_M = 430.0  # approximate terrain height above mean sea level at Al-Kharj
FLIGHT_ENDURANCE_S = 1500.0  # 25 minutes from 100 % to 0 %


@dataclass(frozen=True)
class SurveyPlan:
    frame: LocalFrame
    area_xy: tuple[XY, ...]
    waypoints_xy: tuple[XY, ...]
    length_m: float

    @property
    def waypoints_latlon(self) -> list[LatLon]:
        return [self.frame.to_latlon(x, y) for x, y in self.waypoints_xy]

    @property
    def width_m(self) -> float:
        xmin, _, xmax, _ = bounding_box(self.area_xy)
        return xmax - xmin

    @property
    def height_m(self) -> float:
        _, ymin, _, ymax = bounding_box(self.area_xy)
        return ymax - ymin


def plan_survey(area: Sequence[Sequence[float]], line_spacing_m: float) -> SurveyPlan:
    frame = LocalFrame.centred_on(area)
    area_xy = tuple(frame.to_xy(lat, lon) for lat, lon in area)
    waypoints = tuple(survey_lanes(area_xy, line_spacing_m))
    return SurveyPlan(frame=frame, area_xy=area_xy, waypoints_xy=waypoints, length_m=path_length(waypoints))


@dataclass(frozen=True)
class SimulationConfig:
    area: tuple[LatLon, ...]
    altitude_m: float
    speed_mps: float
    line_spacing_m: float
    soil_type: str
    seed: int
    dt_s: float = 0.2
    ground_elevation_m: float = GROUND_ELEVATION_M


@dataclass(frozen=True)
class Simulation:
    config: SimulationConfig
    plan: SurveyPlan
    scenario: Scenario
    _sensors: SensorModel = field(repr=False)

    @property
    def frame(self) -> LocalFrame:
        return self.plan.frame

    def samples(self) -> Iterator[tuple[FlightSample, SensorSample]]:
        cfg = self.config
        flight = fly(
            self.plan.waypoints_xy,
            cfg.altitude_m,
            cfg.speed_mps,
            cfg.dt_s,
            battery_drain_pct_per_s=100.0 / FLIGHT_ENDURANCE_S,
            rng=random.Random(f"{cfg.seed}:flight"),
        )
        for fs in flight:
            yield fs, self._sensors.sample(fs.x, fs.y, fs.alt_m)

    def sensor_sample(self, x: float, y: float, height_m: float) -> SensorSample:
        """Payload readings at a position flown by something else (PX4), over this scenario's buried objects."""
        return self._sensors.sample(x, y, height_m)


def build_simulation(config: SimulationConfig) -> Simulation:
    plan = plan_survey(config.area, config.line_spacing_m)
    scenario = generate_scenario(plan.area_xy, config.soil_type, config.seed)
    return Simulation(
        config=config,
        plan=plan,
        scenario=scenario,
        _sensors=SensorModel(scenario, noise_seed=config.seed),
    )

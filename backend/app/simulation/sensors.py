"""Synthetic metal-detector (MD) and ground-penetrating-radar (GPR) readings.

Simplified physical models, in arbitrary normalised units:

* MD  ∝ metal mass / stand-off³, where stand-off = sensor height + burial depth,
  so the response weakens with flight altitude and object depth. Soil
  mineralisation adds a smooth background plus white noise.
* GPR ∝ reflection coefficient (dielectric contrast between object and soil)
  × size factor × two-way attenuation exp(-2·α·depth) × spreading loss with altitude.
  α grows with soil moisture/clay, so wet soil weakens the radar return.
  The reading also carries the two-way travel time of the strongest reflector,
  from which depth can later be estimated if the soil permittivity is known.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .scenario import BuriedObject, Scenario, SoilProfile

MD_GAIN = 4.0
GPR_GAIN = 3.0
METAL_REFLECTION = 0.9
REFERENCE_SIZE_M = 0.15
SPEED_OF_LIGHT_M_PER_NS = 0.2998


@dataclass(frozen=True)
class SensorSample:
    md: float
    gpr_amp: float
    gpr_twt_ns: float  # two-way travel time of the strongest reflector


def md_response(obj: BuriedObject, x: float, y: float, height_m: float) -> float:
    if obj.metal_mass <= 0:
        return 0.0
    standoff = height_m + obj.depth_m
    sigma = 0.4 * standoff + obj.size_m / 2
    r2 = (x - obj.x) ** 2 + (y - obj.y) ** 2
    return MD_GAIN * obj.metal_mass / standoff**3 * math.exp(-r2 / (2 * sigma**2))


def reflection_coefficient(obj: BuriedObject, soil: SoilProfile) -> float:
    if obj.permittivity is None:
        return METAL_REFLECTION
    a = math.sqrt(soil.permittivity)
    b = math.sqrt(obj.permittivity)
    return abs(a - b) / (a + b)


def gpr_response(obj: BuriedObject, soil: SoilProfile, x: float, y: float, height_m: float) -> float:
    sigma = 0.25 + 0.2 * height_m + obj.size_m / 2
    # Objects much smaller than the radar wavelength scatter weakly (Rayleigh-like regime).
    size_factor = min(1.0, (obj.size_m / REFERENCE_SIZE_M) ** 2)
    attenuation = math.exp(-2 * soil.gpr_attenuation * obj.depth_m)
    spreading = 1 / (1 + 0.4 * height_m) ** 2
    r2 = (x - obj.x) ** 2 + (y - obj.y) ** 2
    footprint = math.exp(-r2 / (2 * sigma**2))
    return GPR_GAIN * reflection_coefficient(obj, soil) * size_factor * attenuation * spreading * footprint


def two_way_travel_time_ns(depth_m: float, permittivity: float) -> float:
    return 2 * depth_m * math.sqrt(permittivity) / SPEED_OF_LIGHT_M_PER_NS


class SensorModel:
    def __init__(self, scenario: Scenario, noise_seed: int) -> None:
        self._scenario = scenario
        self._rng = random.Random(f"{noise_seed}:sensor-noise")

    def sample(self, x: float, y: float, height_m: float) -> SensorSample:
        sc = self._scenario
        soil = sc.soil

        md = sum(md_response(o, x, y, height_m) for o in sc.objects)
        md += soil.md_background * sc.md_field.value(x, y)
        md += self._rng.gauss(0.0, soil.md_noise)

        contributions = [(gpr_response(o, soil, x, y, height_m), o) for o in sc.objects]
        strongest_amp, strongest = max(contributions, key=lambda c: c[0], default=(0.0, None))
        clutter = soil.gpr_clutter * sc.gpr_field.value(x, y)
        gpr = sum(c for c, _ in contributions) + clutter + self._rng.gauss(0.0, soil.gpr_noise)

        twt_jitter = self._rng.gauss(0.0, 0.05)
        if strongest is not None and strongest_amp > clutter + soil.gpr_noise:
            twt = two_way_travel_time_ns(strongest.depth_m, soil.permittivity) + twt_jitter
        else:
            twt = self._rng.uniform(0.3, 4.0)  # no clear reflector: travel time is clutter

        return SensorSample(md=max(0.0, md), gpr_amp=max(0.0, gpr), gpr_twt_ns=max(0.0, twt))

"""Simulated ground truth: soil conditions and buried objects.

All values are illustrative, order-of-magnitude figures chosen to reproduce the
qualitative behaviour reported in the literature (metal-detector response falls
with stand-off distance, GPR is attenuated by moist clay, mineralised soil makes
metal detectors noisy, low-metal mines are nearly invisible to metal detectors).
They are not calibrated against real sensor hardware.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .geo import XY, bounding_box, point_in_polygon


class ObjectKind(StrEnum):
    METAL_MINE = "metal_mine"
    LOW_METAL_MINE = "low_metal_mine"
    SCRAP_METAL = "scrap_metal"
    ROCK = "rock"


TARGET_KINDS = frozenset({ObjectKind.METAL_MINE, ObjectKind.LOW_METAL_MINE})


@dataclass(frozen=True)
class SoilProfile:
    key: str
    label: str
    permittivity: float  # relative dielectric permittivity (εr)
    moisture: float  # volumetric water content, 0..1
    gpr_attenuation: float  # Np/m, grows with moisture and clay content
    md_noise: float  # metal-detector white noise (std)
    md_background: float  # amplitude of smooth soil-mineralisation response
    gpr_noise: float  # GPR white noise (std)
    gpr_clutter: float  # amplitude of smooth subsurface clutter (stones, layers)
    rock_weight: float  # relative chance that an extra object is a rock


SOIL_PROFILES: dict[str, SoilProfile] = {
    "dry_sand": SoilProfile(
        key="dry_sand",
        label="Dry sand",
        permittivity=4.0,
        moisture=0.05,
        gpr_attenuation=2.0,
        md_noise=0.015,
        md_background=0.02,
        gpr_noise=0.006,
        gpr_clutter=0.008,
        rock_weight=1.0,
    ),
    "wet_clay": SoilProfile(
        key="wet_clay",
        label="Wet clay",
        permittivity=20.0,
        moisture=0.35,
        gpr_attenuation=8.0,
        md_noise=0.02,
        md_background=0.05,
        gpr_noise=0.01,
        gpr_clutter=0.02,
        rock_weight=0.5,
    ),
    "mineralized_rocky": SoilProfile(
        key="mineralized_rocky",
        label="Mineralised rocky soil",
        permittivity=7.0,
        moisture=0.10,
        gpr_attenuation=4.0,
        md_noise=0.04,
        md_background=0.30,
        gpr_noise=0.012,
        gpr_clutter=0.04,
        rock_weight=3.0,
    ),
}


@dataclass(frozen=True)
class BuriedObject:
    id: int
    kind: ObjectKind
    x: float
    y: float
    depth_m: float
    metal_mass: float  # relative metal content (arbitrary units)
    size_m: float  # characteristic diameter
    permittivity: float | None  # None = metallic body (near-total GPR reflection)

    @property
    def is_target(self) -> bool:
        return self.kind in TARGET_KINDS


@dataclass(frozen=True)
class FieldComponent:
    kx: float
    ky: float
    phase: float
    weight: float


@dataclass(frozen=True)
class SmoothField:
    """Spatially smooth random field with values in [0, 1].

    Used for slowly varying soil mineralisation (metal detector) and
    subsurface clutter (GPR), which is what makes a single fixed threshold
    unreliable across a survey area.
    """

    components: tuple[FieldComponent, ...]

    def value(self, x: float, y: float) -> float:
        total_weight = sum(c.weight for c in self.components)
        s = sum(c.weight * math.cos(c.kx * x + c.ky * y + c.phase) for c in self.components)
        return 0.5 + 0.5 * s / total_weight

    @classmethod
    def random(
        cls,
        rng: random.Random,
        n: int = 6,
        min_wavelength_m: float = 6.0,
        max_wavelength_m: float = 20.0,
    ) -> SmoothField:
        components = []
        for _ in range(n):
            wavelength = rng.uniform(min_wavelength_m, max_wavelength_m)
            direction = rng.uniform(0, 2 * math.pi)
            k = 2 * math.pi / wavelength
            components.append(
                FieldComponent(
                    kx=k * math.cos(direction),
                    ky=k * math.sin(direction),
                    phase=rng.uniform(0, 2 * math.pi),
                    weight=rng.uniform(0.5, 1.0),
                )
            )
        return cls(tuple(components))


@dataclass(frozen=True)
class Scenario:
    seed: int
    soil: SoilProfile
    objects: tuple[BuriedObject, ...]
    md_field: SmoothField
    gpr_field: SmoothField


MIN_OBJECTS = 5
MAX_OBJECTS = 8
EDGE_MARGIN_M = 3.0
MIN_SEPARATION_M = 6.0

REQUIRED_KINDS = (
    ObjectKind.METAL_MINE,
    ObjectKind.LOW_METAL_MINE,
    ObjectKind.SCRAP_METAL,
    ObjectKind.ROCK,
)


def _object_properties(kind: ObjectKind, soil: SoilProfile, rng: random.Random) -> dict:
    match kind:
        case ObjectKind.METAL_MINE:
            return dict(
                depth_m=rng.uniform(0.05, 0.20),
                metal_mass=rng.uniform(0.6, 2.0),
                size_m=rng.uniform(0.20, 0.30),
                permittivity=None,
            )
        case ObjectKind.LOW_METAL_MINE:
            # Plastic body with explosive fill and air gaps; only a small firing pin is metal.
            return dict(
                depth_m=rng.uniform(0.03, 0.12),
                metal_mass=rng.uniform(0.003, 0.01),
                size_m=rng.uniform(0.08, 0.14),
                permittivity=rng.uniform(2.2, 2.8),
            )
        case ObjectKind.SCRAP_METAL:
            # Fragments, cans, shrapnel: strong metal response, tiny GPR cross-section.
            return dict(
                depth_m=rng.uniform(0.0, 0.10),
                metal_mass=rng.uniform(0.4, 1.5),
                size_m=rng.uniform(0.02, 0.06),
                permittivity=None,
            )
        case ObjectKind.ROCK:
            magnetic = soil.key == "mineralized_rocky"
            return dict(
                depth_m=rng.uniform(0.05, 0.35),
                metal_mass=rng.uniform(0.02, 0.08) if magnetic else 0.0,
                size_m=rng.uniform(0.20, 0.50),
                permittivity=rng.uniform(6.0, 9.0),
            )
    raise ValueError(f"unknown object kind: {kind}")


def generate_scenario(area_xy: Sequence[XY], soil_type: str, seed: int) -> Scenario:
    """Place 5-8 buried objects inside the area. Deterministic for a given seed."""
    if soil_type not in SOIL_PROFILES:
        raise ValueError(f"unknown soil type: {soil_type}")
    soil = SOIL_PROFILES[soil_type]
    rng = random.Random(f"{seed}:objects")

    count = rng.randint(MIN_OBJECTS, MAX_OBJECTS)
    pool = [ObjectKind.METAL_MINE, ObjectKind.LOW_METAL_MINE, ObjectKind.SCRAP_METAL, ObjectKind.ROCK]
    weights = [1.0, 1.0, 1.5, soil.rock_weight]
    kinds = list(REQUIRED_KINDS) + rng.choices(pool, weights=weights, k=count - len(REQUIRED_KINDS))
    rng.shuffle(kinds)

    xmin, ymin, xmax, ymax = bounding_box(area_xy)
    positions: list[XY] = []
    for _ in range(5000):
        if len(positions) == len(kinds):
            break
        x = rng.uniform(xmin + EDGE_MARGIN_M, xmax - EDGE_MARGIN_M)
        y = rng.uniform(ymin + EDGE_MARGIN_M, ymax - EDGE_MARGIN_M)
        if not point_in_polygon(x, y, area_xy):
            continue
        if all(math.hypot(x - px, y - py) >= MIN_SEPARATION_M for px, py in positions):
            positions.append((x, y))
    if len(positions) < len(kinds):
        raise ValueError("survey area is too small to place the simulated objects")

    objects = tuple(
        BuriedObject(id=i + 1, kind=kind, x=x, y=y, **_object_properties(kind, soil, rng))
        for i, (kind, (x, y)) in enumerate(zip(kinds, positions, strict=True))
    )
    field_rng = random.Random(f"{seed}:fields")
    return Scenario(
        seed=seed,
        soil=soil,
        objects=objects,
        md_field=SmoothField.random(field_rng),
        gpr_field=SmoothField.random(field_rng),
    )

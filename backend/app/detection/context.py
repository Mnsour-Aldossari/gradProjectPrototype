"""Survey conditions -> condition profile used by the adaptive detector."""

from __future__ import annotations

from dataclasses import dataclass

from .params import AdaptiveParams

# Nominal relative permittivity per soil type (typical literature values), used to
# convert GPR travel time to depth. The classifier does not see the simulator's
# internal soil model; it only knows the soil type selected when planning the mission.
SOIL_PERMITTIVITY: dict[str, float] = {
    "dry_sand": 4.0,
    "wet_clay": 20.0,
    "mineralized_rocky": 7.0,
}
SOIL_LABELS: dict[str, str] = {
    "dry_sand": "Dry sand",
    "wet_clay": "Wet clay",
    "mineralized_rocky": "Mineralised rocky soil",
}
DEFAULT_PERMITTIVITY = 6.0


@dataclass(frozen=True)
class SurveyContext:
    soil_type: str
    altitude_m: float
    speed_mps: float
    line_spacing_m: float
    sample_period_s: float = 0.2


@dataclass(frozen=True)
class ConditionProfile:
    soil_type: str
    soil_label: str
    permittivity: float
    md_reliability: float
    gpr_reliability: float
    radar_trusted: bool
    half_window: int  # samples on each side for the local background
    guard: int  # samples on each side excluded from the background
    link_radius_m: float  # hits closer than this belong to the same object
    notes: tuple[str, ...]


def condition_profile(context: SurveyContext, params: AdaptiveParams) -> ConditionProfile:
    rel = params.soil(context.soil_type)
    sample_spacing_m = max(context.speed_mps * context.sample_period_s, 1e-3)
    half_window = max(5, round(params.background_window_m / 2 / sample_spacing_m))
    guard = min(half_window - 3, max(1, round(params.guard_m / sample_spacing_m)))
    radar_trusted = rel.gpr >= params.radar_trust

    permittivity = SOIL_PERMITTIVITY.get(context.soil_type, DEFAULT_PERMITTIVITY)
    notes = [
        f"Metal-detector threshold: {params.k_md / rel.md:.1f} x local spread (reliability {rel.md:.2f}).",
        f"Radar threshold: {params.k_gpr:.1f} x local spread (reliability {rel.gpr:.2f}); "
        + (
            "a missing radar reflection counts as evidence against a solid object."
            if radar_trusted
            else "radar is attenuated, so a missing radar reflection is weak evidence."
        ),
        f"Depth from radar travel time assumes relative permittivity {permittivity:g}.",
    ]
    if context.altitude_m > 2.0:
        notes.append("High sensor altitude weakens both sensors; small objects may be missed.")

    return ConditionProfile(
        soil_type=context.soil_type,
        soil_label=SOIL_LABELS.get(context.soil_type, context.soil_type),
        permittivity=permittivity,
        md_reliability=rel.md,
        gpr_reliability=rel.gpr,
        radar_trusted=radar_trusted,
        half_window=half_window,
        guard=guard,
        # Adjacent survey passes over one object must merge into one detection.
        link_radius_m=1.25 * context.line_spacing_m,
        notes=tuple(notes),
    )

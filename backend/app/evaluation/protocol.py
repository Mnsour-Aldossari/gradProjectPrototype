"""Evaluation protocol constants. See docs/EVALUATION_PROTOCOL.md.

Tuning seeds are the only data used to choose parameters. Evaluation seeds are
used only to report results, after the parameters have been frozen.
"""

from app.simulation import DEMO_AREA

TUNING_SEEDS: tuple[int, ...] = tuple(range(1000, 1020))
EVALUATION_SEEDS: tuple[int, ...] = tuple(range(2000, 2030))
SOIL_TYPES: tuple[str, ...] = ("dry_sand", "wet_clay", "mineralized_rocky")

STANDARD_SURVEY = {
    "area": DEMO_AREA,
    "altitude_m": 1.5,
    "speed_mps": 2.0,
    "line_spacing_m": 2.0,
}
MATCH_RADIUS_M = 1.5

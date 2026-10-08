"""Evaluation protocol of the version 2 adaptive detector. See docs/EVALUATION_PROTOCOL_V2.md.

Version 2 is calibrated on the tuning seeds only (protocol.py), at the five settings below. It is then evaluated
once, with version 1 and the baseline, on fresh seeds that nothing has used before, and replaces version 1 in the
app only if the adoption rule written here before that run holds.
"""

from .protocol import ESTIMATE_SEEDS, EVALUATION_SEEDS, TUNING_SEEDS

EVALUATION_SEEDS_V2: tuple[int, ...] = tuple(range(4000, 4030))
assert not set(EVALUATION_SEEDS_V2) & (set(TUNING_SEEDS) | set(EVALUATION_SEEDS) | set(ESTIMATE_SEEDS))

# (height m, speed m/s, lane spacing m), the standard survey first; the same five as the calibration's.
EVALUATION_SETTINGS: tuple[tuple[float, float, float], ...] = (
    (1.5, 2.0, 2.0),
    (1.0, 1.0, 1.0),
    (0.75, 2.0, 2.0),
    (1.5, 1.0, 1.0),
    (2.0, 2.0, 2.0),
)

# Version 2 replaces version 1 in the app only if, on the fresh seeds, all three hold: over the five settings pooled
# it finds at least this share more of the mines, with no more false alarms; and at the standard setting it does not
# find more than this share fewer.
ADOPTION = {
    "recall_gain_all": 0.02,
    "recall_loss_standard": 0.02,
}

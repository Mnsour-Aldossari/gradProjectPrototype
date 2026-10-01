"""Adaptive thresholding: local background (rolling median) and spread (MAD).

Each reading is compared with the readings around it along the flight track,
so slowly varying soil responses (mineralisation, moisture, layering) raise
the local background instead of triggering detections.

* CFAR-style guard cells: readings within `guard` samples of the reading
  under test are left out of its background estimate, so a buried object
  does not raise its own threshold.
* The spread is an upper semi-MAD: the median of the deviations *above* the
  local median. Sensor outputs are amplitudes with a floor at zero, which
  squeezes the lower half of the distribution; detections are positive
  anomalies, so the upper half is the relevant (and undistorted) side. For
  Gaussian noise it equals the ordinary MAD.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

MAD_TO_SIGMA = 1.4826
MIN_SCALE = 1e-4
MIN_TRAINING = 6


def _median_sorted(values: Sequence[float]) -> float:
    n = len(values)
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


def robust_scores(
    values: Sequence[float], half_window: int, guard: int, start: int = 0, stop: int | None = None
) -> tuple[list[float], list[float]]:
    """For each index: residual = value - local median, z = residual / (1.4826 * local upper semi-MAD)."""
    n = len(values)
    stop = n if stop is None else stop
    residuals, zs = [], []
    for i in range(start, stop):
        lo, hi = max(0, i - half_window), min(n, i + half_window + 1)
        training = values[lo : max(lo, i - guard)] + values[min(hi, i + guard + 1) : hi]
        if len(training) < MIN_TRAINING:  # very start of a survey
            training = values[lo:hi]
        window = sorted(training)
        median = _median_sorted(window)
        upper = [v - median for v in window if v > median]  # already sorted
        mad = _median_sorted(upper) if upper else 0.0
        residual = values[i] - median
        residuals.append(residual)
        zs.append(residual / max(MAD_TO_SIGMA * mad, MIN_SCALE))
    return residuals, zs


class RollingRobustScaler:
    """Incremental robust_scores for streaming data.

    A score is final once half_window later readings exist; final scores are
    cached and only the most recent ones are recomputed on each call.
    """

    def __init__(self, half_window: int, guard: int) -> None:
        self.half_window = half_window
        self.guard = guard
        self._values: list[float] = []
        self._residuals: list[float] = []
        self._zs: list[float] = []

    def extend(self, values: Iterable[float]) -> None:
        self._values.extend(values)

    def scores(self) -> tuple[list[float], list[float]]:
        n = len(self._values)
        final_upto = max(0, n - self.half_window)
        if len(self._zs) < final_upto:
            r, z = robust_scores(self._values, self.half_window, self.guard, len(self._zs), final_upto)
            self._residuals.extend(r)
            self._zs.extend(z)
        r_tail, z_tail = robust_scores(self._values, self.half_window, self.guard, len(self._zs), n)
        return self._residuals + r_tail, self._zs + z_tail

# Evaluation Results — Adaptive v2 vs. v1 vs. Baseline

> **النتائج على بيانات محاكاة.** Results on simulated data. The simulator is not calibrated against real sensors; the numbers compare the methods inside the simulation and do not predict field performance.

Generated 2026-10-08 by `backend/scripts/evaluate_v2.py`, once, from the frozen detectors, as [EVALUATION_PROTOCOL_V2.md](EVALUATION_PROTOCOL_V2.md) says. Version 1's results ([EVALUATION_RESULTS.md](EVALUATION_RESULTS.md)) are unchanged.

- Fresh evaluation seeds 4000–4029 × 3 soils × 5 settings = 450 simulated surveys; match radius 1.5 m; reported: high + needs verification (baseline: high).

## Adoption rule

| Condition | v2 vs v1 | Met |
|---|---|---|
| Recall over the five settings at least 0.02 above v1's | 0.825 vs 0.727 | Yes |
| False alarms over the five settings not more than v1's | 407 vs 401 | No |
| Recall at the standard setting not more than 0.02 below v1's | 0.781 vs 0.719 | Yes |

**Decision: v1 stays in the app.**

## Height 1.5 m, speed 2.0 m/s, lanes 2.0 m (standard)

| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |
|---|---|---|---|---|---|---|---|---|
| Dry sand | Fixed threshold (baseline) | 93 | 35 | 43 | 0.376 | 0.449 | 0.409 | 0/52 |
| Dry sand | Adaptive v1 | 93 | 75 | 43 | 0.806 | 0.636 | 0.711 | 34/52 |
| Dry sand | Adaptive v2 | 93 | 79 | 20 | 0.849 | 0.798 | 0.823 | 38/52 |
| Wet clay | Fixed threshold (baseline) | 98 | 37 | 47 | 0.378 | 0.440 | 0.407 | 0/54 |
| Wet clay | Adaptive v1 | 98 | 65 | 23 | 0.663 | 0.739 | 0.699 | 31/54 |
| Wet clay | Adaptive v2 | 98 | 73 | 28 | 0.745 | 0.723 | 0.734 | 41/54 |
| Mineralised rocky soil | Fixed threshold (baseline) | 83 | 39 | 45 | 0.470 | 0.464 | 0.467 | 0/43 |
| Mineralised rocky soil | Adaptive v1 | 83 | 57 | 10 | 0.687 | 0.851 | 0.760 | 17/43 |
| Mineralised rocky soil | Adaptive v2 | 83 | 62 | 18 | 0.747 | 0.775 | 0.761 | 22/43 |
| **All soils** | Fixed threshold (baseline) | 274 | 111 | 135 | 0.405 | 0.451 | 0.427 | 0/149 |
| **All soils** | Adaptive v1 | 274 | 197 | 76 | 0.719 | 0.722 | 0.720 | 82/149 |
| **All soils** | Adaptive v2 | 274 | 214 | 66 | 0.781 | 0.764 | 0.773 | 101/149 |

## Height 1.0 m, speed 1.0 m/s, lanes 1.0 m

| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |
|---|---|---|---|---|---|---|---|---|
| Dry sand | Fixed threshold (baseline) | 93 | 41 | 63 | 0.441 | 0.394 | 0.416 | 0/52 |
| Dry sand | Adaptive v1 | 93 | 90 | 39 | 0.968 | 0.698 | 0.811 | 49/52 |
| Dry sand | Adaptive v2 | 93 | 91 | 25 | 0.978 | 0.784 | 0.871 | 50/52 |
| Wet clay | Fixed threshold (baseline) | 98 | 44 | 64 | 0.449 | 0.407 | 0.427 | 0/54 |
| Wet clay | Adaptive v1 | 98 | 65 | 15 | 0.663 | 0.812 | 0.730 | 51/54 |
| Wet clay | Adaptive v2 | 98 | 85 | 32 | 0.867 | 0.726 | 0.791 | 50/54 |
| Mineralised rocky soil | Fixed threshold (baseline) | 83 | 40 | 47 | 0.482 | 0.460 | 0.471 | 0/43 |
| Mineralised rocky soil | Adaptive v1 | 83 | 64 | 2 | 0.771 | 0.970 | 0.859 | 29/43 |
| Mineralised rocky soil | Adaptive v2 | 83 | 75 | 22 | 0.904 | 0.773 | 0.833 | 35/43 |
| **All soils** | Fixed threshold (baseline) | 274 | 125 | 174 | 0.456 | 0.418 | 0.436 | 0/149 |
| **All soils** | Adaptive v1 | 274 | 219 | 56 | 0.799 | 0.796 | 0.798 | 129/149 |
| **All soils** | Adaptive v2 | 274 | 251 | 79 | 0.916 | 0.761 | 0.831 | 135/149 |

## Height 0.75 m, speed 2.0 m/s, lanes 2.0 m

| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |
|---|---|---|---|---|---|---|---|---|
| Dry sand | Fixed threshold (baseline) | 93 | 40 | 48 | 0.430 | 0.455 | 0.442 | 0/52 |
| Dry sand | Adaptive v1 | 93 | 65 | 40 | 0.699 | 0.619 | 0.657 | 31/52 |
| Dry sand | Adaptive v2 | 93 | 76 | 38 | 0.817 | 0.667 | 0.734 | 35/52 |
| Wet clay | Fixed threshold (baseline) | 98 | 43 | 49 | 0.439 | 0.467 | 0.453 | 0/54 |
| Wet clay | Adaptive v1 | 98 | 41 | 13 | 0.418 | 0.759 | 0.539 | 36/54 |
| Wet clay | Adaptive v2 | 98 | 78 | 39 | 0.796 | 0.667 | 0.726 | 39/54 |
| Mineralised rocky soil | Fixed threshold (baseline) | 83 | 40 | 51 | 0.482 | 0.440 | 0.460 | 0/43 |
| Mineralised rocky soil | Adaptive v1 | 83 | 40 | 2 | 0.482 | 0.952 | 0.640 | 18/43 |
| Mineralised rocky soil | Adaptive v2 | 83 | 63 | 31 | 0.759 | 0.670 | 0.712 | 23/43 |
| **All soils** | Fixed threshold (baseline) | 274 | 123 | 148 | 0.449 | 0.454 | 0.451 | 0/149 |
| **All soils** | Adaptive v1 | 274 | 146 | 55 | 0.533 | 0.726 | 0.615 | 85/149 |
| **All soils** | Adaptive v2 | 274 | 217 | 108 | 0.792 | 0.668 | 0.725 | 97/149 |

## Height 1.5 m, speed 1.0 m/s, lanes 1.0 m

| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |
|---|---|---|---|---|---|---|---|---|
| Dry sand | Fixed threshold (baseline) | 93 | 41 | 59 | 0.441 | 0.410 | 0.425 | 0/52 |
| Dry sand | Adaptive v1 | 93 | 85 | 49 | 0.914 | 0.634 | 0.749 | 44/52 |
| Dry sand | Adaptive v2 | 93 | 90 | 26 | 0.968 | 0.776 | 0.861 | 49/52 |
| Wet clay | Fixed threshold (baseline) | 98 | 44 | 62 | 0.449 | 0.415 | 0.431 | 0/54 |
| Wet clay | Adaptive v1 | 98 | 85 | 26 | 0.867 | 0.766 | 0.813 | 50/54 |
| Wet clay | Adaptive v2 | 98 | 85 | 33 | 0.867 | 0.720 | 0.787 | 50/54 |
| Mineralised rocky soil | Fixed threshold (baseline) | 83 | 40 | 47 | 0.482 | 0.460 | 0.471 | 0/43 |
| Mineralised rocky soil | Adaptive v1 | 83 | 68 | 12 | 0.819 | 0.850 | 0.834 | 28/43 |
| Mineralised rocky soil | Adaptive v2 | 83 | 72 | 21 | 0.867 | 0.774 | 0.818 | 32/43 |
| **All soils** | Fixed threshold (baseline) | 274 | 125 | 168 | 0.456 | 0.427 | 0.441 | 0/149 |
| **All soils** | Adaptive v1 | 274 | 238 | 87 | 0.869 | 0.732 | 0.795 | 122/149 |
| **All soils** | Adaptive v2 | 274 | 247 | 80 | 0.901 | 0.755 | 0.822 | 131/149 |

## Height 2.0 m, speed 2.0 m/s, lanes 2.0 m

| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |
|---|---|---|---|---|---|---|---|---|
| Dry sand | Fixed threshold (baseline) | 93 | 18 | 24 | 0.194 | 0.429 | 0.267 | 0/52 |
| Dry sand | Adaptive v1 | 93 | 70 | 72 | 0.753 | 0.493 | 0.596 | 29/52 |
| Dry sand | Adaptive v2 | 93 | 78 | 25 | 0.839 | 0.757 | 0.796 | 37/52 |
| Wet clay | Fixed threshold (baseline) | 98 | 20 | 21 | 0.204 | 0.488 | 0.288 | 0/54 |
| Wet clay | Adaptive v1 | 98 | 72 | 38 | 0.735 | 0.655 | 0.692 | 32/54 |
| Wet clay | Adaptive v2 | 98 | 70 | 31 | 0.714 | 0.693 | 0.704 | 38/54 |
| Mineralised rocky soil | Fixed threshold (baseline) | 83 | 28 | 24 | 0.337 | 0.538 | 0.415 | 0/43 |
| Mineralised rocky soil | Adaptive v1 | 83 | 54 | 17 | 0.651 | 0.761 | 0.701 | 14/43 |
| Mineralised rocky soil | Adaptive v2 | 83 | 53 | 18 | 0.639 | 0.746 | 0.688 | 18/43 |
| **All soils** | Fixed threshold (baseline) | 274 | 66 | 69 | 0.241 | 0.489 | 0.323 | 0/149 |
| **All soils** | Adaptive v1 | 274 | 196 | 127 | 0.715 | 0.607 | 0.657 | 75/149 |
| **All soils** | Adaptive v2 | 274 | 201 | 74 | 0.734 | 0.731 | 0.732 | 93/149 |

## All five settings pooled

| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |
|---|---|---|---|---|---|---|---|---|
| **All** | Fixed threshold (baseline) | 1370 | 550 | 694 | 0.401 | 0.442 | 0.421 | 0/745 |
| **All** | Adaptive v1 | 1370 | 996 | 401 | 0.727 | 0.713 | 0.720 | 493/745 |
| **All** | Adaptive v2 | 1370 | 1130 | 407 | 0.825 | 0.735 | 0.777 | 557/745 |

## Secondary: version 1's evaluation seeds 2000–2029, standard setting

Version 2 was designed knowing version 1's limitations on these seeds, so this table is for continuity only.

| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |
|---|---|---|---|---|---|---|---|---|
| Dry sand | Fixed threshold (baseline) | 86 | 38 | 53 | 0.442 | 0.418 | 0.429 | 0/47 |
| Dry sand | Adaptive v1 | 86 | 68 | 52 | 0.791 | 0.567 | 0.660 | 29/47 |
| Dry sand | Adaptive v2 | 86 | 73 | 27 | 0.849 | 0.730 | 0.785 | 34/47 |
| Wet clay | Fixed threshold (baseline) | 97 | 38 | 46 | 0.392 | 0.452 | 0.420 | 0/56 |
| Wet clay | Adaptive v1 | 97 | 65 | 20 | 0.670 | 0.765 | 0.714 | 31/56 |
| Wet clay | Adaptive v2 | 97 | 72 | 35 | 0.742 | 0.673 | 0.706 | 38/56 |
| Mineralised rocky soil | Fixed threshold (baseline) | 74 | 36 | 51 | 0.486 | 0.414 | 0.447 | 0/38 |
| Mineralised rocky soil | Adaptive v1 | 74 | 54 | 10 | 0.730 | 0.844 | 0.783 | 18/38 |
| Mineralised rocky soil | Adaptive v2 | 74 | 55 | 13 | 0.743 | 0.809 | 0.775 | 19/38 |
| **All soils** | Fixed threshold (baseline) | 257 | 112 | 150 | 0.436 | 0.427 | 0.432 | 0/141 |
| **All soils** | Adaptive v1 | 257 | 187 | 82 | 0.728 | 0.695 | 0.711 | 78/141 |
| **All soils** | Adaptive v2 | 257 | 200 | 75 | 0.778 | 0.727 | 0.752 | 91/141 |

Run time: 14 s.

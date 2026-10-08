# Evaluation Protocol — Adaptive Detection, Version 2

**All results produced under this protocol are on simulated data.** The simulator is not calibrated against real
sensors; results compare the methods inside the simulation, not how they would perform in the field.

This document, the version 2 code and its frozen parameters were committed **before** version 2 was run on its
evaluation seeds. The git history shows that order. Version 1's protocol, parameters and results
([EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md), [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md)) are unchanged.

## 1. Why a version 2

Version 1 was evaluated at one survey geometry (1.5 m, 2 m/s, 2 m lanes). The accuracy estimate added for planning
(`backend/app/detection/accuracy_table.json`, on its own seeds) showed that with version 1 flying lower loses metal
mines: its body-ratio rule (radar response over metal response) was calibrated at 1.5 m, and lower down the metal
detector's response grows much faster than the radar's, so metal mines were taken for scrap. Version 1's known
limitations also include rocks reported as radar-only reflectors and many low-metal mines missed.

## 2. What version 2 changes (`backend/app/detection/adaptive_v2.py`)

1. **Height-corrected body ratio.** Each sensor's response is divided by its gain at the reading's height relative to
   1.5 m (metal detector about (height + 0.1 m)^-3, radar (1 + 0.4 height)^-2), so the ratio means the same at any
   height. These curves are a sensor characterisation: in the field they are measured once per sensor over a test
   target; here they are the simulated sensors'.
2. **Shallower limit for reflectors without metal** (`max_reflector_depth_m`, calibrated): a radar reflector with no
   metal response deeper than this is a stone or a natural structure. Metal objects keep version 1's 0.30 m.
3. **Matched filter along the track** (`smooth`, calibrated on/off): each sensor's readings averaged with their
   neighbours within the footprint before the local background.

Everything else is version 1's: local adaptive thresholds with guard cells, clustering, the categories, the soil
reliabilities (not calibrated again).

## 3. Data split

| Set | Seeds | Used for |
|---|---|---|
| Tuning | `1000`–`1019` (as version 1) | developing version 2 and calibrating its parameters |
| Estimate | `3000`–`3029` | the planning estimate only (`scripts/accuracy_table.py`); not used by version 2's development |
| **Evaluation v2** | **`4000`–`4029`** | **this evaluation only, once; never used before** |
| Evaluation v1 | `2000`–`2029` | secondary table only (see 6) |

Seeds are in `backend/app/evaluation/protocol.py` and `protocol_v2.py`. Soils: dry sand, wet clay, mineralised rocky.

Survey settings (height m, speed m/s, lane spacing m), the same for calibration and evaluation, the standard first:
(1.5, 2, 2), (1.0, 1, 1), (0.75, 2, 2), (1.5, 1, 1), (2.0, 2, 2). The 60 m × 40 m test field, 5 Hz sampling.

Scoring as version 1: a mine counts as found when a high-priority or needs-verification candidate lies within
1.5 m; any other reported candidate is a false alarm.

## 4. Calibration (tuning seeds only)

Script: `backend/scripts/calibrate_v2.py`. Output: `docs/calibration_result_v2.json`. 300 tuning surveys (20 seeds ×
3 soils × 5 settings).

**Objective:** the most mines found, pooled, with **no more false alarms than version 1** on the same surveys; ties
go to fewer false alarms, then grid order. A first run used version 1's objective (F1). It cut false alarms by more
than half but found fewer mines than version 1 at the standard setting. Missing a mine costs more than a false
alarm, so the objective was changed, on tuning data, before any evaluation.

| Parameter | Grid | Frozen value |
|---|---|---|
| `k_md` | 2, 2.5, 3, 4, 5, 6, 8, 10 | **3.0** |
| `k_gpr` | 3, 3.5, 4, 5, 6, 7, 8, 10, 12 | **4.0** |
| `body_ratio` (at 1.5 m) | 0.05, 0.075, 0.1, 0.15, 0.2 | **0.1** |
| `max_reflector_depth_m` | 0.06, 0.08, 0.1, 0.12, 0.15, 0.2, 0.3 | **0.12** |
| `smooth` | off, on | **off** |

The grids of `k_md`, `k_gpr` and the depth started at 3, 4 and 0.12; the best sat on a lower edge in a run, so they
were extended downward and the calibration run again (tuning data). The final values are inside the grids.

**The matched filter was not chosen:** within version 1's false alarms it found fewer mines (best with it: 772 of
1005, k_md 5, k_gpr 8) than without it (828).

**Tuning-set results** (for reference only, not the evaluation):

| Setting | v1 recall | v2 recall | v1 false alarms | v2 false alarms | v1 low-metal | v2 low-metal |
|---|---|---|---|---|---|---|
| 1.5 m, 2 m/s, 2 m (standard) | 0.756 | 0.796 | 49 | 45 | 61/101 | 69/101 |
| 1.0 m, 1 m/s, 1 m | 0.771 | 0.925 | 41 | 54 | 85/101 | 94/101 |
| 0.75 m, 2 m/s, 2 m | 0.527 | 0.786 | 47 | 72 | 56/101 | 65/101 |
| 1.5 m, 1 m/s, 1 m | 0.826 | 0.881 | 56 | 48 | 77/101 | 88/101 |
| 2.0 m, 2 m/s, 2 m | 0.741 | 0.731 | 83 | 46 | 52/101 | 62/101 |
| **Pooled** | **0.724** | **0.824** | **276** | **265** | | |

## 5. Adoption rule (fixed before evaluation)

Version 2 replaces version 1 in the app (live detection while a mission flies, and the ROS 2 detector node) only if,
on the evaluation v2 seeds, **all three** hold:

1. pooled over the five settings, its recall is at least **0.02** above version 1's;
2. pooled over the five settings, it raises **no more false alarms** than version 1;
3. at the standard setting, its recall is at most **0.02** below version 1's.

Otherwise version 1 stays, and version 2 is reported as tried. Either way the results are reported as they come
out; neither the simulator nor the parameters are changed afterwards.

## 6. What is reported

Script: `backend/scripts/evaluate_v2.py`, run once. Output: `docs/EVALUATION_RESULTS_V2.md` and
`docs/evaluation_v2.json`: per setting and soil, for the baseline, version 1 and version 2, the mines found, false
alarms, recall, precision, F1 and low-metal mines found; the five settings pooled; the adoption rule's three checks
and the decision. Secondary: the three methods on version 1's evaluation seeds at the standard setting, for
continuity with version 1's results. Version 2 was designed knowing version 1's limitations on those seeds, so that
table is not evidence for version 2.

## 7. Known limitations

- Everything in version 1's protocol (synthetic sensors, nominal permittivity equal to the simulator's, …).
- The height correction uses the simulated sensors' height response; real sensors need theirs measured.
- `max_reflector_depth_m` relies on anti-personnel mines lying shallow (here at most 0.12 m for low-metal mines); a
  deeper low-metal mine would be called clutter.
- Five survey settings are evaluated, all on one test-field geometry.

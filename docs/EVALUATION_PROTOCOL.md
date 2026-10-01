# Evaluation Protocol — Baseline vs. Adaptive Detection

**All results produced under this protocol are on simulated data.** The simulator is not calibrated
against real sensors; results show how the two methods behave relative to each other inside the
simulation, not how they would perform in the field.

This document was written and committed, together with the frozen parameters, **before** any
detector was run on the evaluation seeds. The git history shows that order.

## 1. Data split

| Set | Seeds | Scenarios | Used for |
|---|---|---|---|
| Tuning | `1000`–`1019` | 20 seeds × 3 soils = 60 | Developing the detector and calibrating every parameter |
| Evaluation | `2000`–`2029` | 30 seeds × 3 soils = 90 | Reporting results and the mandatory tests only |

Seeds are defined in `backend/app/evaluation/protocol.py`. Seeds used during Day 1 development
(0–19 for structural tests, and 3, 4, 5, 7, 11, 23, 42) are in neither set. The demo scenario will use a
seed outside both sets.

Soil types: `dry_sand`, `wet_clay`, `mineralized_rocky`.

Survey (identical for every scenario): 60 m × 40 m test area (`DEMO_AREA`), sensor height 1.5 m,
speed 2 m/s, line spacing 2 m, 5 Hz sampling. Each scenario contains 5–8 buried objects with at
least one of each kind.

## 2. Ground truth and scoring

- **Targets:** `metal_mine`, `low_metal_mine`. **Non-targets:** `scrap_metal`, `rock`.
- **Reported:** a candidate in category HIGH or SUSPECT, because both would send personnel to verify.
  CLUTTER is not reported. The baseline only produces HIGH or CLUTTER.
- **Matching:** reported candidates are taken in descending confidence order. A candidate within
  **1.5 m** of an unmatched target is a true positive, and each target can be matched only once.
  Every other reported candidate is a **false alarm**. It is attributed to the nearest object within
  1.5 m (`scrap_metal`, `rock`, or `duplicate` for an already-matched target), or to `background`.
- **Metrics:** recall = TP / targets; precision = TP / reported; F1; false-alarm count. These are
  reported per soil and pooled, together with per-object-kind outcomes: `reported`, `clutter`
  (only CLUTTER candidates nearby) or `none`.

Implementation: `backend/app/detection/evaluation.py`, `backend/app/evaluation/harness.py`.

## 3. Calibration (tuning seeds only)

Script: `backend/scripts/calibrate.py`. Full output: `docs/calibration_result.json`.

**Objective, identical for both methods:** F1 of reported detections pooled over all 60 tuning
scenarios. Ties are broken by higher recall, then by grid order. The search is exhaustive over these grids:

| Method | Parameter | Grid | Frozen value |
|---|---|---|---|
| Baseline | metal-detector threshold (one value for all soils) | 0.10 – 0.80, step 0.02 | **0.46** |
| Adaptive | `k_md` | 3, 4, 5, 6 | **4.0** |
| Adaptive | `k_gpr` | 3, 4, 5, 6 | **5.0** |
| Adaptive | `body_ratio` | 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4 | **0.1** |
| Adaptive | reliability (md, gpr), per soil | each 0.5, 0.75, 1.0 | dry sand **(0.5, 1.0)**, wet clay **(0.5, 0.75)**, mineralised rocky **(0.5, 1.0)** |

The baseline gets a single fixed threshold because that is what it represents: one rule for all
conditions. Its threshold is still chosen to give the baseline its best possible tuning score.

`body_ratio` was first searched over 0.1–0.4. The optimum was on the lower edge, so the grid was extended
downward and the search re-run (still tuning data only). The optimum stayed at 0.1.

**Tuning-set results** (pooled; for reference only, not the evaluation):

| Method | Recall | Precision | F1 | False alarms |
|---|---|---|---|---|
| Baseline | 0.478 | 0.589 | 0.527 | 67 |
| Adaptive | 0.756 | 0.756 | 0.756 | 49 |
| Adaptive, same reliabilities forced for all soils (ablation) | 0.736 | 0.759 | 0.747 | — |

**Finding from calibration, stated plainly:** the per-soil reliability weights contribute little in
this simulation. Calibration chose the same metal-detector reliability (0.5) for every soil, and only
the radar reliability differs (wet clay 0.75). Forcing one shared setting lowers tuning F1 by only
0.009. Most of the difference from the baseline comes from:

- the local adaptive thresholds (rolling background with guard cells), and
- combining radar with the metal detector (body-ratio rule, radar-only reflectors, depth from soil permittivity).

### Design constants (not calibrated)

background window 20 m along track; guard zone ±2 m; spread = upper semi-MAD; max mine depth 0.30 m;
radar trusted when reliability ≥ 0.75; minimum 2 hits per candidate; evidence cap 3;
clustering radius 1.25 × line spacing (2.5 m). Baseline: clustering radius 2.5 m, minimum 2 hits.

The detector structure was developed while looking at tuning seeds only. Two changes came from that:

- the upper semi-MAD, because amplitudes have a floor at zero, which shrank the ordinary MAD;
- the CFAR guard zone, because without it an object raised its own threshold.

## 4. Mandatory tests and pass criteria (fixed before evaluation)

File: `backend/tests/test_evaluation_protocol.py`. Evaluation seeds × all three soils, frozen parameters.

| ID | Test | Pass criterion |
|---|---|---|
| T1 | Adaptive raises fewer false alarms than baseline | pooled adaptive false alarms < pooled baseline false alarms |
| T2 | Low-metal mines are found by radar | more than 50 % of low-metal mines are reported by the adaptive method, **and** every such report is radar-driven (radar evidence ≥ 1, metal evidence < 1) |
| T3 | Scrap metal is classified as likely clutter | of the scrap objects with any adaptive candidate within 1.5 m, more than 50 % have only CLUTTER candidates |

Plus single-object checks on fixed seeds (`backend/tests/test_adaptive.py`): a lone low-metal mine is
reported through radar, a lone scrap fragment is CLUTTER, and a lone metal mine is HIGH.

**If a test fails, the result is reported as it is.** Neither the simulator nor the parameters are
changed to make it pass.

## 5. Known limitations

- Synthetic sensor models with illustrative parameters; not validated against hardware.
- The classifier knows the soil type selected at mission planning and uses a nominal permittivity for
  it. In the simulator that nominal value equals the true value, so depth estimates are optimistic.
- Rocks and low-metal mines produce similar radar-only responses. The adaptive method reports both
  for verification, which accounts for most of its false alarms.
- One survey geometry (fixed altitude, speed and spacing) is evaluated.

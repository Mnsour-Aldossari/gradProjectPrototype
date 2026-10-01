# Evaluation Results — Baseline vs. Adaptive Detection

> **النتائج على بيانات محاكاة.** Results on simulated data. The simulator is not calibrated against real sensors; the numbers compare the two methods inside the simulation and do not predict field performance.

Generated 2026-10-02 by `backend/scripts/evaluate.py` from the frozen detectors. The web page (Evaluation) shows the same report. Protocol, seeds and calibration: [EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md).

- Evaluation seeds 2000–2029 × 3 soil types = 90 simulated surveys (tuning seeds 1000–1019 were used for calibration only).
- Survey: sensor height 1.5 m, speed 2.0 m/s, line spacing 2.0 m; match radius 1.5 m.
- Reported detections: adaptive: high + suspect; baseline: high. Every output is a potential detection for verification by trained personnel.

## Results by soil type

| Soil | Method | Targets | Found | Missed | False alarms | Recall | Precision | F1 |
|---|---|---|---|---|---|---|---|---|
| Dry sand | Fixed threshold (baseline) | 86 | 38 | 48 | 53 | 0.442 | 0.418 | 0.429 |
| Dry sand | Adaptive | 86 | 68 | 18 | 52 | 0.791 | 0.567 | 0.660 |
| Wet clay | Fixed threshold (baseline) | 97 | 38 | 59 | 46 | 0.392 | 0.452 | 0.420 |
| Wet clay | Adaptive | 97 | 65 | 32 | 20 | 0.670 | 0.765 | 0.714 |
| Mineralised rocky soil | Fixed threshold (baseline) | 74 | 36 | 38 | 51 | 0.486 | 0.414 | 0.447 |
| Mineralised rocky soil | Adaptive | 74 | 54 | 20 | 10 | 0.730 | 0.844 | 0.783 |
| **All soils** | Fixed threshold (baseline) | 257 | 112 | 145 | 150 | 0.436 | 0.427 | 0.432 |
| **All soils** | Adaptive | 257 | 187 | 70 | 82 | 0.728 | 0.695 | 0.711 |

False-alarm causes (all soils):

- Fixed threshold (baseline): scrap metal 150
- Adaptive: rock 40, scrap metal 34, background 8

## Known limitations — حدود معروفة

- **No improvement in dry sand.** In dry sand the adaptive method raised 52 false alarms against the baseline's 53. It removes scrap-metal alarms but reports buried rocks as radar-only reflectors instead (35 of its dry-sand false alarms are rocks).
- **Many low-metal mines are not found.** 63 of 141 low-metal mines (45 %) were not reported by the adaptive method. The baseline, which uses only the metal detector, reported none of them.
- **More metal mines missed than the baseline.** The adaptive method missed 7 of 116 metal mines; the baseline missed 4.
- **Borderline case: low-metal mine 7 cm deep in dry sand.** Its radar signal sits right at the frozen threshold. It was reported in 1 of 3 fixed seeds. This is kept as a known limitation; parameters were not re-tuned.

Borderline case per seed (Lone low-metal mine, 7 cm deep, 11 cm wide, in dry sand (adaptive method)):

- seed 501: reported (suspect), radar at 2.15x threshold
- seed 502: no candidate
- seed 503: only a 1-sample response at 1.05x radar threshold, treated as noise

## Mandatory tests

| ID | Test | Value | Result |
|---|---|---|---|
| T1 | Adaptive raises fewer false alarms than the baseline | 82 vs 150 | Pass |
| T2 | More than half of the low-metal mines are found, all through radar | 78 / 141 (55 %), 0 not radar-driven | Pass |
| T3 | More than half of the scrap objects are classified as likely clutter | 153 / 187 (82 %) | Pass |

## Frozen parameters used

- Baseline: metal-detector threshold 0.46
- Adaptive: k_md 4.0, k_gpr 5.0, body ratio 0.1; reliabilities dry_sand (md 0.5, gpr 1.0), wet_clay (md 0.5, gpr 0.75), mineralized_rocky (md 0.5, gpr 1.0)

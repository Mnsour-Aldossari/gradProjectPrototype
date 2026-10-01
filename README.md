# UAV-Based Landmine Detection System — Prototype

Graduation project prototype (Software Engineering, Prince Sattam Bin Abdulaziz University).
A simulated UAV surveys an area with a metal detector (MD) and ground-penetrating radar (GPR);
the system stores the mission data, classifies **potential detections**, and presents them for
verification by trained personnel. Nothing in this system confirms a landmine.

> All UAV flights and sensor readings in this prototype are **simulated**. No flight hardware is used.

## Repository layout — who owns what

| Folder | Responsibility | Depends on |
|---|---|---|
| `backend/app/simulation/` | Simulated world: soil profiles, buried objects (ground truth), lawnmower flight path, MD/GPR sensor models | nothing else in the app |
| `backend/app/uav/` | **UAV interface layer.** `TelemetrySource` protocol + `SimulatedSource`. `px4_mavlink_source.py` is a documented stub for a future PX4 phase | `simulation/` |
| `backend/app/detection/` | Detection & classification library: fixed-threshold baseline and the adaptive classifier (condition profile, CFAR-style thresholds, reliability-weighted decision), plus scoring against ground truth. Pure Python, no FastAPI/DB imports | nothing else in the app |
| `backend/app/evaluation/` | Evaluation protocol (tuning vs. evaluation seeds) and harness that runs simulated surveys through both methods | `simulation/`, `detection/` |
| `backend/scripts/calibrate.py` | Parameter calibration on tuning seeds only | `evaluation/` |
| `backend/app/api/` | REST endpoints, WebSocket hub (`/ws/missions/{id}`), auth, background mission runner (live adaptive detections) | all of the above + DB |
| `backend/app/models.py`, `db.py` | Database tables (SQLModel). Portable: SQLite by default, PostgreSQL via `DATABASE_URL` | — |
| `backend/tests/` | PyTest suite | — |
| `web/` | React + TypeScript dashboard: mission planning, live satellite map, detection review and verification. Responsive, used on phones by field staff | REST/WebSocket API only |
| `docs/` | `EVALUATION_PROTOCOL.md` (seeds, calibration), `EVALUATION_RESULTS.md` (generated results), `calibration_result.json`; architecture and demo script planned for Day 3 | — |

Data flow: `simulation` → `uav.SimulatedSource` (MAVLink-shaped frames) → `api.runner` → database + `detection.AdaptiveDetector` (every 5 s of flight) → WebSocket events → web.

## Running the backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # on Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs .

## Running the web dashboard

```bash
cd web
npm install
npm run dev          # http://localhost:5180 (forwards /api and /ws to the backend on :8000)
```

Start the backend first. Satellite imagery is loaded from Esri and needs an internet connection. Demo accounts (supervisor and field operator) are defined in
`backend/app/seed.py` and are test credentials only.

Settings (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/uav.db` | e.g. `postgresql+psycopg://user:pass@localhost:5432/uav` |
| `SIM_SPEED_FACTOR` | `10` | default playback speed for missions (1 = real time) |
| `SECRET_KEY` | dev value | token signing key |

The code uses only portable column types so switching to PostgreSQL needs no code change; this has not yet been
run against a PostgreSQL server in this prototype.

## Tests and calibration

```bash
cd backend
.venv/Scripts/python -m pytest                  # includes mandatory tests T1-T3 on the evaluation seeds
.venv/Scripts/python -m scripts.calibrate       # re-runs calibration on tuning seeds (does not change code)
.venv/Scripts/python -m scripts.evaluate        # regenerates docs/EVALUATION_RESULTS.md (same report as the Evaluation page)
```

Known limitation, marked `xfail(strict=True)` (see `docs/EVALUATION_PROTOCOL.md` section 6):
`test_lone_low_metal_mine_is_reported_through_radar` fails for seeds 502 and 503; seed 501 runs as a normal test.

## Main API endpoints

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/login` | anyone |
| GET/POST | `/api/missions` | read: any user, create: supervisor |
| GET | `/api/missions/{id}` | any user (includes stored-data counts) |
| POST | `/api/missions/{id}/start` | supervisor; body `{"speed_factor": 10}` |
| POST | `/api/missions/demo` | supervisor — creates and starts the fixed demo scenario (seed 2000, dry sand, 20×) |
| GET | `/api/missions/{id}/telemetry` | any user |
| GET | `/api/missions/{id}/detections?method=adaptive` | any user |
| GET | `/api/missions/{id}/profile` | any user — how the adaptive classifier is configured for the mission |
| WS | `/ws/missions/{id}?token=...` | snapshot, then live telemetry, detections, alerts, status |
| PATCH | `/api/detections/{id}` | any user; `pending` / `confirmed_by_team` / `false_alarm` |
| GET | `/api/evaluation` | any user — baseline vs adaptive on the evaluation seeds (simulated data) |

## Status

- [x] Day 1 — simulator, TelemetrySource, baseline (fixed-threshold) detector, persistence, tests
- [x] Day 2 — adaptive detection & classification (calibrated on tuning seeds, frozen), WebSocket live updates, React dashboard
- [ ] Day 3 — evaluation page (baseline vs adaptive on simulated data), demo scenario, docs

Not implemented (documented future phases only): PX4 SITL + Gazebo, ROS 2, Flutter mobile app.

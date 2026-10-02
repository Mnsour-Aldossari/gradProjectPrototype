# UAV-Based Landmine Detection System — Prototype

Graduation project prototype (Software Engineering, Prince Sattam Bin Abdulaziz University).
A simulated UAV surveys an area with a metal detector (MD) and ground-penetrating radar (GPR);
the system stores the mission data, classifies **potential detections**, and presents them for
verification by trained personnel. Nothing in this system confirms a landmine.

> All UAV flights and sensor readings in this prototype are **simulated**. No flight hardware is used.

The current version is a prototype and is not ready for public deployment; see
[Security Hardening (Not Implemented)](docs/ARCHITECTURE.md#security-hardening-not-implemented).

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
| `docs/` | `ARCHITECTURE.md` (report section 4.1, diagrams, future phases, security notes), `DEMO_SCRIPT.md` (Arabic demo script), `EVALUATION_PROTOCOL.md` (seeds, calibration), `EVALUATION_RESULTS.md` (generated results), `calibration_result.json` | — |

Data flow: `simulation` → `uav.SimulatedSource` (MAVLink-shaped frames) → `api.runner` → database + `detection.AdaptiveDetector` (every 5 s of flight) → WebSocket events → web.

## Requirements

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.14 (3.14.5) | Older versions have not been tried. |
| Node.js + npm | Node 26 (26.3.0) | Needed only for the web dashboard. Older versions have not been tried. |
| Internet connection | — | For `pip install` / `npm install`, and for the satellite imagery (Esri) on the map. |

Checked on Windows 11 in a fresh folder, with PowerShell and Git Bash (`.venv/Scripts/...` with forward slashes
works in both). They were not tried in `cmd.exe`; use PowerShell. On Linux/macOS use `.venv/bin/`
instead of `.venv/Scripts/` (not tested).

## Running from scratch on Windows

1. Get the code. The GitHub repository is not public, so cloning it needs access to it:

   ```bash
   git clone https://github.com/Mnsour-Aldossari/gradProjectPrototype.git uav-landmine-prototype
   ```

2. Backend, in a first terminal:

   ```bash
   cd uav-landmine-prototype/backend
   python -m venv .venv
   .venv/Scripts/pip install -r requirements.txt
   .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
   ```

   On first start the backend creates the SQLite database `backend/uav.db`, adds the two demo accounts, and
   generates the token signing key `backend/.secret_key`. Health check: http://localhost:8000/api/health .
   Interactive API docs: http://localhost:8000/docs (open without login; development only).

3. Web dashboard, in a second terminal (start the backend first):

   ```bash
   cd uav-landmine-prototype/web
   npm install
   npm run dev
   ```

   Open http://localhost:5180 . The dev server forwards `/api` and `/ws` to the backend on port 8000.

4. Sign in with one of the demo accounts (next section). The supervisor lands on **Missions**; the field operator is
   sent to the field view `/field`.

## Demo accounts (test credentials only)

Two demo accounts are created on first start: `supervisor` (mission supervisor) and `field` (field operator).
Their passwords are in `backend/app/seed.py`. They are **test credentials for local demos only** and must not be
used on any machine reachable by others.

Field view: field operators land on `/field` after signing in, a mobile-first page (full-screen map,
high-priority alerts, nearest potential detections by distance, verification, bottom navigation Map / Alerts /
Status). When location permission is refused or the device is more than 2 km from the survey area, distances are
measured from a fixed **test location** inside the survey area, marked on the map. The device location is used only
in the browser and is never sent to the server.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///.../backend/uav.db` | e.g. `postgresql+psycopg://user:pass@localhost:5432/uav` |
| `SIM_SPEED_FACTOR` | `10` | default playback speed for missions (1 = real time) |
| `SECRET_KEY` | random, saved in `backend/.secret_key` | token signing key; if unset, one is generated on first start and reused (git-ignored) |

The code uses only portable column types so switching to PostgreSQL needs no code change; this has not yet been
run against a PostgreSQL server in this prototype.

## Tests and type check

```bash
cd backend
.venv/Scripts/python -m pytest
```

Expected result: **124 passed, 2 xfailed**. This includes the mandatory tests T1–T3 on the evaluation seeds. The
two expected failures are a known limitation, marked `xfail(strict=True)` (see `docs/EVALUATION_PROTOCOL.md`
section 6): `test_lone_low_metal_mine_is_reported_through_radar` fails for seeds 502 and 503; seed 501 runs as a
normal test.

```bash
cd web
npm run typecheck
```

Calibration and evaluation scripts (both **overwrite files in `docs/`**, so they were not re-run while this README
was reviewed):

```bash
cd backend
.venv/Scripts/python -m scripts.calibrate       # re-runs calibration on tuning seeds, writes docs/calibration_result.json
.venv/Scripts/python -m scripts.evaluate        # regenerates docs/EVALUATION_RESULTS.md (same report as the Evaluation page)
```

## Resetting the local database before a demo

```bash
cd backend
.venv/Scripts/python -m scripts.reset_db          # dry run: lists what would be deleted, changes nothing
.venv/Scripts/python -m scripts.reset_db --yes    # copies uav.db to backups/, then resets
```

The reset removes all missions, telemetry, sensor readings and detections and leaves only the two demo users
(supervisor and field operator, re-created by the same seeding the server runs at startup). Stop the backend before
running it. `backups/` is git-ignored. It only touches the database in `DATABASE_URL`; the automatic backup is made
for SQLite only. (Not re-run while this README was reviewed.)

## Main API endpoints

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/login` | anyone |
| GET | `/api/auth/me` | any user |
| GET/POST | `/api/missions` | read: any user, create: supervisor |
| GET | `/api/missions/history` | any user — finished missions with potential-detection counts per category and verification progress |
| GET | `/api/missions/{id}` | any user (includes stored-data counts) |
| POST | `/api/missions/{id}/start` | supervisor; body `{"speed_factor": 10}` |
| POST | `/api/missions/demo` | supervisor — creates and starts the fixed demo scenario (seed 2000, dry sand, 20×) |
| GET | `/api/missions/{id}/telemetry` | any user |
| GET | `/api/missions/{id}/detections?method=adaptive` | any user |
| GET | `/api/missions/{id}/profile` | any user — how the adaptive classifier is configured for the mission |
| WS | `/ws/missions/{id}?token=...` | snapshot, then live telemetry, detections, alerts, status |
| PATCH | `/api/detections/{id}` | any user; `pending` / `confirmed_by_team` / `false_alarm` |
| GET | `/api/evaluation` | any user — baseline vs adaptive on the evaluation seeds (simulated data) |

## What works and what does not

Works (implemented and tested with PyTest and/or in the browser):

- Simulated surveys (soil profiles, buried objects, flight path, MD/GPR readings) and the `TelemetrySource` layer.
- Fixed-threshold baseline and adaptive classification, calibrated on tuning seeds and evaluated on separate seeds.
- FastAPI backend with SQLite, login with supervisor / field-operator roles, live WebSocket updates.
- Supervisor dashboard: missions, new mission planning, demo scenario, live map, detection details and
  verification, comparison with the baseline, mission history, evaluation page.
- Field view `/field` at phone size: alerts, nearest potential detections, verification.

Not working, not run, or only partly checked:

| Item | Status |
|---|---|
| Docker | `docker-compose.yml`, `backend/Dockerfile`, `web/Dockerfile`, `web/nginx.conf` are written, but **the images have not been built and the containers have not been run** (Docker Desktop's engine was not running). Only `docker compose config` was run, and it accepts the compose file. |
| Postman | `postman/uav-prototype.postman_collection.json` (six requests) **has not been opened in Postman**. The same requests and test scripts were replayed against the running backend with a small Node script that mimics `pm`, and all passed. |
| PWA install | The web app manifest and icons were checked in the browser. The service worker (`web/public/sw.js`, network-first, never caches `/api` or `/ws`) could not be registered in the built-in test browser, and installing on a real phone has not been tried. |
| PostgreSQL | Supported through `DATABASE_URL` by design, never run against a PostgreSQL server. |
| PX4 SITL + Gazebo | Not implemented. `backend/app/uav/px4_mavlink_source.py` is a documented stub only. |
| ROS 2 | Not implemented; future architecture only. |
| Flutter mobile app | Not implemented; the field view is a web page (PWA) instead. |
| Security hardening | Not implemented (rate limiting, HTTPS, security headers, token revocation, …); see `docs/ARCHITECTURE.md`. |

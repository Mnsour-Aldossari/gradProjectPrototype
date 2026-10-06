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
| `backend/app/uav/` | **UAV interface layer.** `TelemetrySource` protocol + `SimulatedSource`, and `Px4MavlinkSource` (PX4 SITL + Gazebo over MAVLink, through MAVSDK; optional) with its vehicle-free parts in `px4_plan.py` | `simulation/` |
| `backend/app/detection/` | Detection & classification library: fixed-threshold baseline and the adaptive classifier (condition profile, CFAR-style thresholds, reliability-weighted decision), plus scoring against ground truth. Pure Python, no FastAPI/DB imports | nothing else in the app |
| `backend/app/evaluation/` | Evaluation protocol (tuning vs. evaluation seeds) and harness that runs simulated surveys through both methods | `simulation/`, `detection/` |
| `backend/scripts/calibrate.py` | Parameter calibration on tuning seeds only | `evaluation/` |
| `backend/app/api/` | REST endpoints, WebSocket hub (`/ws/missions/{id}`), auth, background mission runner (live adaptive detections) | all of the above + DB |
| `backend/app/models.py`, `db.py` | Database tables (SQLModel). Portable: SQLite by default, PostgreSQL via `DATABASE_URL` | — |
| `backend/tests/` | PyTest suite | — |
| `web/` | React + TypeScript dashboard: mission planning, live satellite map, detection review and verification. Responsive, used on phones by field staff | REST/WebSocket API only |
| `docs/` | `ARCHITECTURE.md` (report section 4.1, diagrams, future phases, security notes), `DEMO_SCRIPT.md` (Arabic demo script), `EVALUATION_PROTOCOL.md` (seeds, calibration), `EVALUATION_RESULTS.md` (generated results), `calibration_result.json` | — |

Data flow: `simulation` → `uav.SimulatedSource` (MAVLink-shaped frames), or PX4 → `uav.Px4MavlinkSource` → `api.runner` → database + `detection.AdaptiveDetector` (every 5 s of flight) → WebSocket events → web.

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

## Flying with PX4 SITL + Gazebo (optional)

A mission can be flown by the PX4 autopilot in the Gazebo simulator instead of the built-in simulator. PX4 flies the
survey; the metal-detector and radar readings still come from the project's sensor model, taken at PX4's position.

1. Start Docker Desktop and wait for **Engine running**.
2. Start PX4 + Gazebo with its home at the survey area (here the test field near Al-Kharj). The first run downloads
   the image (about 3.3 GB, 10 GB on disk). Keep `-it`: without a terminal, PX4's console fills the log.

   ```bash
   docker run -dit --rm --name px4-sitl -e PX4_HOME_LAT=24.13950 -e PX4_HOME_LON=47.26200 -e PX4_HOME_ALT=430 jonasvautherin/px4-gazebo-headless:1.17.0
   ```

3. Once, in the backend folder: `.venv/Scripts/pip install -r requirements-px4.txt` (MAVSDK), then restart the
   backend.
4. Open a planned mission. In the Flight card choose **Fly with: PX4 SITL**, then **Start survey**.
5. Stop PX4 when done: `docker stop px4-sitl`.

Notes:

- PX4 flies in real time, so playback speed does not apply. Lane ends are slower than the plan, so the remaining time
  follows PX4's own pace. The 60 × 40 m demo field takes more than 11 minutes.
- The survey area must be within 900 m of PX4's home (PX4's limit). For another area, restart the container with
  `PX4_HOME_LAT` / `PX4_HOME_LON` at that area; otherwise Start says so and the mission stays planned.
- If PX4 is not running, Start reports it after about 10 s and the mission stays planned. One PX4 mission flies at
  a time; the simulator is not affected. **Run demo scenario** always uses the simulator.
- After the survey PX4 returns to launch and lands. If the backend stops during a flight, PX4's link-loss failsafe
  holds for 5 s, then returns and lands.

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
| `PX4_URL` | `udpin://0.0.0.0:14540` | where MAVSDK listens for PX4, for missions flown with PX4 |

The code uses only portable column types so switching to PostgreSQL needs no code change; this has not yet been
run against a PostgreSQL server in this prototype.

## Tests and type check

```bash
cd backend
.venv/Scripts/python -m pytest
```

Expected result: **145 passed, 2 xfailed** with `requirements-px4.txt` installed (without it one PX4 test is
skipped: 144 passed, 1 skipped). This includes the mandatory tests T1–T3 on the evaluation seeds. The
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
| POST | `/api/missions/{id}/start` | supervisor; body `{"speed_factor": 10, "uav_source": "simulated"}` or `{"uav_source": "px4"}`; 503 with the reason if PX4 cannot fly it |
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
- PX4 SITL + Gazebo (PX4 1.17.0, headless Docker image, Windows 11): chosen per mission with **Fly with**. Flown end
  to end on 20 × 20 m surveys: all 12 waypoints in order, median 0.06 m from the planned lanes (max 0.62 m),
  1.46–1.54 m high for 1.5 m planned, readings and detections stored like a simulated survey. Also checked: PX4 not
  running, an area 87 km from home, a second flight right after the first, a flight interrupted by a backend stop.
- Fixed-threshold baseline and adaptive classification, calibrated on tuning seeds and evaluated on separate seeds.
- FastAPI backend with SQLite, login with supervisor / field-operator roles, live WebSocket updates.
- Supervisor dashboard: missions, new mission planning, demo scenario, live map, detection details and
  verification, comparison with the baseline, mission history, evaluation page.
- Field view `/field` at phone size: alerts, nearest potential detections, verification.
- Display settings: light, dark or device theme, small / normal / large text and comfortable / compact density,
  chosen under **Display** (in the sidebar, or on the Status tab of `/field`) and saved per user in the browser on
  that device; **Reset to default** restores them. They change the look only, never what a user can see.
- Page layout, saved the same way: **Collapse menu** folds the sidebar to icons; on a mission page **Customize**
  reorders (drag or arrows), folds and hides the cards and resizes the column or the map, and **Expand map** gives the
  map the whole page. Flight cannot be hidden, so Start survey stays reachable; **Reset this page** and
  **Reset to default** undo it.

Not working, not run, or only partly checked:

| Item | Status |
|---|---|
| Docker | `docker-compose.yml`, `backend/Dockerfile`, `web/Dockerfile`, `web/nginx.conf` are written, but **the images have not been built and the containers have not been run** (Docker Desktop's engine was not running). Only `docker compose config` was run, and it accepts the compose file. |
| Postman | `postman/uav-prototype.postman_collection.json` (six requests) **has not been opened in Postman**. The same requests and test scripts were replayed against the running backend with a small Node script that mimics `pm`, and all passed. |
| PWA install | The web app manifest and icons were checked in the browser. The service worker (`web/public/sw.js`, network-first, never caches `/api` or `/ws`) could not be registered in the built-in test browser, and installing on a real phone has not been tried. |
| PostgreSQL | Supported through `DATABASE_URL` by design, never run against a PostgreSQL server. |
| PX4 SITL + Gazebo | Flown only in the headless Docker image (no 3D window) and only on small surveys; not tried with the Gazebo window, QGroundControl, the full demo field or a real vehicle. MD/GPR come from the project's sensor model at PX4's position, not from Gazebo sensors. MAVSDK's mission progress came back empty with PX4 1.17, so the waypoint being flown is taken from PX4's position. |
| ROS 2 | Not implemented; future architecture only. |
| Flutter mobile app | Not implemented; the field view is a web page (PWA) instead. |
| Security hardening | Not implemented (rate limiting, HTTPS, security headers, token revocation, …); see `docs/ARCHITECTURE.md`. |
 
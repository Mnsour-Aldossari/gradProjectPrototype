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
| `backend/app/simulation/` | Simulated world: soil profiles, buried objects (ground truth), lawnmower lanes cut to the area's outline, MD/GPR sensor models | nothing else in the app |
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
PX4 SITL runs on the PC that runs the backend, in one of two ways, and the backend starts it itself:

- **PX4 SITL**: the headless Docker image, without a window.
- **PX4 SITL + Gazebo window**: PX4-Autopilot built in WSL (Windows 11), with Gazebo's 3D window on the desktop.

Once:

1. In the backend folder: `.venv/Scripts/pip install -r requirements-px4.txt` (MAVSDK), then restart the backend.
2. Without a window: start Docker Desktop and download the image (about 3.3 GB, 10 GB on disk):
   `docker pull jonasvautherin/px4-gazebo-headless:1.17.0`.
3. With Gazebo's window: install Ubuntu 22.04 in WSL (`wsl --install -d Ubuntu-22.04`), then in Ubuntu build PX4
   once (30–60 minutes):

   ```bash
   git clone https://github.com/PX4/PX4-Autopilot.git --recursive
   bash ./PX4-Autopilot/Tools/setup/ubuntu.sh
   cd PX4-Autopilot && make px4_sitl gz_x500
   ```

   The last command opens Gazebo; close it with Ctrl+C. Then turn on WSL's mirrored networking, so PX4 in WSL
   reaches the backend. In PowerShell:

   ```powershell
   Set-Content -Path "$env:USERPROFILE\.wslconfig" -Value "[wsl2]`nnetworkingMode=mirrored"
   wsl --shutdown
   ```

   Another distribution or folder: `PX4_GAZEBO_DISTRO`, `PX4_GAZEBO_DIR` (Settings).

Each mission:

4. Open a planned mission. In the Flight card choose **Fly with: PX4 SITL** or **PX4 SITL + Gazebo window**, then
   **Start survey**. PX4 takes off at **H**, by default 5 m outside the area before the first lane, and lands back
   there. **Set on map** next to *Takeoff* or *Landing* moves H, or adds a separate landing point **L** (each within
   900 m of the survey; both can be dragged; a point inside the area is flagged). An orange notice lists what the
   chosen option needs installed, with links; **Got it** hides it until the page is opened again, **Don't show
   again** hides it for that user in this browser, and **What PX4 needs** brings it back.
5. If the chosen PX4 is off, or more than 2 m from H, the backend starts it at H first, and stops the other one so
   that only one PX4 answers: about 30 s for Gazebo's window, about a minute for Docker. For Docker it runs only
   `docker stop px4-sitl` and `docker run` of the image above with the point's coordinates; for WSL, a fixed script
   with the coordinates as numbers. Gazebo's window then stays open between missions, also when the backend stops;
   closing it stops PX4 too. Set `PX4_MANAGE_DOCKER=0` to turn all this off: PX4 then flies from where it is, or
   Start says which `PX4_HOME_LAT` / `PX4_HOME_LON` to start it with for a chosen point.
6. Stop PX4 when done: close Gazebo's window, or `docker stop px4-sitl`.

Notes:

- PX4 flies in real time, so playback speed does not apply. Lane ends are slower than the plan, so the remaining time
  follows PX4's own pace. The 60 × 40 m demo field takes more than 11 minutes.
- H and L must be within 900 m of the survey (PX4's limit). With `PX4_MANAGE_DOCKER=0`, PX4's own home must be too:
  start PX4 with `PX4_HOME_LAT` / `PX4_HOME_LON` at that area; otherwise Start says so and the mission stays planned.
- With `PX4_MANAGE_DOCKER=0` (or a real vehicle), if PX4 is not running Start reports it after about 10 s and the
  mission stays planned. One PX4 mission flies at a time; the simulator is not affected. **Run demo scenario** always
  uses the simulator.
- Gazebo's ground is an empty plane: the potential detections are shown in the app (map and 3D view), from the
  project's sensor model, not in Gazebo.
- After the survey PX4 flies on at the survey height to L, or back to H, and lands there; the map follows it
  (Flying to landing point / Returning home, no readings) and the mission is Completed once it is down. **Return
  Home** during the survey uses PX4's return to launch: it climbs to PX4's return height first (30 m by default),
  then lands at H. If the backend stops during a flight, PX4's link-loss failsafe holds for 5 s, then
  returns and lands.
- After a restart at the takeoff point, PX4 takes off only once its position has held still there for 10 s (a new
  PX4 SITL starts at its default home in Zurich and jumps).

## Planning a survey area

On **New mission**, draw the area with **Rectangle** (two opposite corners), **Circle** (the centre, then a point on
the edge) or **Free shape** (a click per corner; click the first corner or double-click to finish; Backspace removes
the last corner, Escape cancels). Then drag the corners, or a circle's centre and edge, to adjust it. While drawing
and editing, the outline is checked by the backend with the same rules as **Create mission** (each side 20–300 m, a
path of at most 15 km, an outline that does not cross itself, room for the simulated objects), and the lanes the UAV
will fly are drawn on the map. Lanes are cut to the outline; for a rectangle they are exactly the same as before, so
the evaluation and the demo scenario are unchanged.

## Flight controls during a survey

While a survey flies, the supervisor's Flight card has **Pause / Resume**, **Return Home** and **Land**, for the
simulator and PX4 alike:

- **Pause** holds the UAV where it is (PX4: Hold mode) and takes no readings; **Resume** continues the survey from
  there.
- **Return Home** flies back to where the survey started and lands; **Land** lands where the UAV is. Both ask for
  confirmation, as the survey cannot be resumed afterwards. Once the UAV is down the mission is **Stopped**: what was
  scanned, and its potential detections, are kept and shown in History.
- The field view shows Paused, Returning home or Landing; only the supervisor has the buttons.

## 3D view

The **3D** button on the mission map (supervisor) opens `/missions/{id}/3d`, laid out after the "Mission view"
design in the app's own colours (the bars and panels follow the light or dark theme; the scene is always dark):

- **Scene:** a dim ground, the area as a low translucent wall, the planned lanes, the track flown as a glowing line at
  its real height, the ground scanned, the UAV with its sensor footprint and heading, a diamond pin wherever a
  potential detection was reported (same colours as the map), a 5 m safety buffer drawn round high-priority ones
  (for display only), and PX4's H and L points. Labels follow the UAV and the detections.
- **Top bar:** cameras (**3D Orbit**, **Top-down**, **Follow UAV**), the flight clock and, while the survey flies,
  Pause / Return Home / Land.
- **Mission panel:** area coverage with the lane and time left, height, ground speed, battery, source, the live
  metal-detector and radar signal, and **Layers** to show or hide the flown path, planned lanes, scanned area, sensor
  footprint, safety buffers, likely clutter and the satellite imagery (off by default). The choices are kept per user
  in the browser.
- **Detections panel:** the reported detections with their score, distance from the UAV and when the UAV passed them;
  a selected one shows its depth, evidence and status, with the same verification buttons as the mission page.
- Compass, zoom, fit, recenter on the UAV, a scale bar, and a **timeline** with the detections marked on it: live
  while the survey flies; once it has ended a replay (1×–20×, or dragged), each pin appearing when the UAV first passed
  within half a lane spacing of it.
- On a tablet the panels open from the top bar; on a phone as sheets.

It is a visual view, built in the browser with three.js from the same data as the map, and replaces the Gazebo
window for watching a survey. The flight itself is the simulator's or PX4's; the ground is flat (no terrain heights),
and buried objects are not shown, only what was detected. The page loads three.js only when opened.

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
| `DATABASE_URL` | `sqlite:///.../backend/uav.db` | e.g. `postgresql+psycopg://user:pass@127.0.0.1:5432/uav` (see **PostgreSQL** below) |
| `DATABASE_UI_URL` | unset | an http(s) address of a page for browsing the database (e.g. NocoDB at `http://localhost:8082`); when set, supervisors get a **Database** link in the menu that opens it in a new tab. Not shown to the field operator, and not in `/api/health` |
| `TEST_DATABASE_URL` | unset | tests only: a PostgreSQL server (any database); each test then gets a schema of its own there, dropped afterwards. Unset: tests use temporary SQLite files |
| `SIM_SPEED_FACTOR` | `10` | default playback speed for missions (1 = real time) |
| `SECRET_KEY` | random, saved in `backend/.secret_key` | token signing key; if unset, one is generated on first start and reused (git-ignored) |
| `PX4_MANAGE_DOCKER` | `1` | `0`: never start or restart PX4 SITL at a mission's takeoff point, neither the Docker container nor Gazebo's window in WSL (each is off anyway without the `docker` / `wsl` command) |
| `PX4_GAZEBO_DISTRO` | `Ubuntu-22.04` | the WSL distribution where PX4-Autopilot is built, for **PX4 SITL + Gazebo window** |
| `PX4_GAZEBO_DIR` | `PX4-Autopilot` | PX4-Autopilot's folder in that distribution, in the user's home or an absolute path |
| `PX4_URL` | `udpin://0.0.0.0:14540` | where MAVSDK listens for PX4, for missions flown with PX4 |

## PostgreSQL (optional)

SQLite stays the default: without `DATABASE_URL` nothing changes and `backend/uav.db` is used. In the app, the
supervisor's **Database** menu item opens a page with these steps (copyable commands, which database is running now);
once `DATABASE_UI_URL` is set it opens that address instead, in a new tab. To run on PostgreSQL
instead, start a server and point the backend at it. For a trial, in Docker:

```bash
docker run -d --name uav-postgres -e POSTGRES_USER=uav -e POSTGRES_PASSWORD=uav -e POSTGRES_DB=uav -p 5433:5432 -v uav-pgdata:/var/lib/postgresql/data postgres:17
```

Then in the terminal that starts the backend (cmd), before it:

```bash
set DATABASE_URL=postgresql+psycopg://uav:uav@127.0.0.1:5433/uav
```

The tables are created on the first start and the demo accounts added; the database starts empty, and the missions
in `uav.db` stay there. To go back to SQLite, start the backend without `DATABASE_URL`. `GET /api/health` says which
one is running (`"database": "postgresql"` or `"sqlite"`). Use `127.0.0.1`, not `localhost`: on the PC where this was
tried, `localhost` made the connection hang. The whole stack on PostgreSQL: `docker compose -f docker-compose.yml
-f docker-compose.postgres.yml up --build -d` (the database has no published port; set `POSTGRES_PASSWORD` for
anything but a local trial).

To browse the tables in the browser, run a web tool next to PostgreSQL, e.g. NocoDB (it asks for a local account on
first use):

```bash
docker run -d --name uav-nocodb -p 8082:8080 -e NC_ALLOW_LOCAL_EXTERNAL_DBS=true -v uav-nocodb-data:/usr/app/data nocodb/nocodb:latest
```

In NocoDB: **Create base**, **Connect to external database**, PostgreSQL, host `host.docker.internal`, port `5433`,
and the user, password and database used above. Then start the backend with `set DATABASE_UI_URL=http://localhost:8082`
for the **Database** link. `NC_ALLOW_LOCAL_EXTERNAL_DBS` lets NocoDB reach local addresses; do not use it on a server
open to the internet. The `users` table holds the password hashes: do not show it to others.

The code uses only portable column types. Run the tests on PostgreSQL with `TEST_DATABASE_URL` set to the server
(a database in it; the tests create and drop their own schemas).

## Tests and type check

```bash
cd backend
.venv/Scripts/python -m pytest
```

Expected result: **192 passed, 1 skipped, 2 xfailed** with `requirements-px4.txt` installed (the skipped one runs
only on PostgreSQL, with `TEST_DATABASE_URL` set: **193 passed, 2 xfailed**; without MAVSDK two PX4 tests are skipped
too). This includes the mandatory tests T1–T3 on the evaluation seeds. The
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
| GET | `/api/missions/history` | any user — finished missions (completed, stopped, failed) with potential-detection counts per category and verification progress |
| GET | `/api/missions/{id}` | any user (includes stored-data counts) |
| POST | `/api/missions/{id}/start` | supervisor; body `{"speed_factor": 10, "uav_source": "simulated"}`, `{"uav_source": "px4"}` or `{"uav_source": "px4", "gazebo": true}` (Gazebo's window, WSL); 503 with the reason if PX4 cannot fly it |
| POST | `/api/missions/check` | supervisor; the same body as creating a mission; returns the lanes and the problems for that outline without storing anything |
| PUT | `/api/missions/{id}/takeoff` | supervisor; body `{"lat": …, "lon": …}` (or `{}` for the default, 5 m outside the survey start) on a planned mission; 422 if over 900 m from the survey start |
| PUT | `/api/missions/{id}/landing` | supervisor; the same body (or `{}`: land at the takeoff point); 422 if over 900 m from the survey end |
| POST | `/api/missions/{id}/control` | supervisor; body `{"action": "pause" \| "resume" \| "return" \| "land"}` during a flight; 409 if the mission is not flying or the command does not apply now |
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
- PX4 SITL + Gazebo window (PX4-Autopilot v1.18.0-beta1 built in WSL Ubuntu 22.04, Gazebo Harmonic 8.15, Windows 11),
  started from the Flight card: Gazebo opened in 25–30 s with nothing running, and closed and reopened at an H moved
  6 m in 27 s; take-off 0–2 cm from H; a full 20 × 20 m survey landed 2 cm from H without climbing above 1.5 m.
  Choosing PX4 SITL afterwards closed Gazebo and started the Docker container (it was off) at H in 25–36 s, and
  back again; closing Gazebo's window (its process stopped) stopped PX4 too; Gazebo stayed open while the backend
  was stopped.
- Flight controls (Pause, Resume, Return Home, Land): with the simulator, tested with PyTest and in the browser
  (desktop and phone size); with PX4 SITL + Gazebo (headless Docker image), tried by hand in the browser.
- Fixed-threshold baseline and adaptive classification, calibrated on tuning seeds and evaluated on separate seeds.
- FastAPI backend with SQLite, login with supervisor / field-operator roles, live WebSocket updates.
- Supervisor dashboard: missions, new mission planning, demo scenario, live map, detection details and
  verification, comparison with the baseline, mission history, evaluation page.
- Field view `/field` at phone size: alerts, nearest potential detections, verification.
- 3D view (supervisor): live and replay, checked in the browser at desktop and phone size, light and dark, with the
  simulator; also opened while PX4 flew in Gazebo's window (live view, Land from its top bar).
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
| Docker | `docker-compose.yml`, `backend/Dockerfile`, `web/Dockerfile`, `web/nginx.conf`: the images were built and the containers run with `docker compose up --build -d` (Docker Desktop, Windows 11), also with `docker-compose.postgres.yml`; on http://localhost:8080 `/api/health` answered ok, signing in worked and the demo scenario ran to the end with its data stored (on PostgreSQL), and the data survived a restart of the backend container. Not tried: a hosted deployment of the containers. |
| Postman | `postman/uav-prototype.postman_collection.json` (six requests) **has not been opened in Postman**. The same requests and test scripts were replayed against the running backend with a small Node script that mimics `pm`, and all passed. |
| PWA install | The web app manifest and icons were checked in the browser. The service worker (`web/public/sw.js`, network-first, never caches `/api` or `/ws`) could not be registered in the built-in test browser, and installing on a real phone has not been tried. |
| PostgreSQL | Run against PostgreSQL 17 in Docker: all tests pass on it (`TEST_DATABASE_URL`), a database from an older version gets its new columns, a demo mission, verification, history and evaluation work, and the data survives a restart. Not tried: PostGIS, a hosted PostgreSQL (e.g. Render's), a large amount of data, and moving the missions of an existing `uav.db` over. |
| PX4 SITL + Gazebo | Flown only on small surveys, in the headless Docker image and in Gazebo's window (WSL, one PC); not tried on the full demo field or with a real vehicle. QGroundControl, started by hand, followed the flights from PX4 SITL (not through the app). MD/GPR come from the project's sensor model at PX4's position, not from Gazebo sensors. MAVSDK's mission progress came back empty with PX4 1.17, so the waypoint being flown is taken from PX4's position. Once (1 of the 6 test flights of the Gazebo window, never before in this project) the backend stopped right after a landing with a crash in native code (exit code 139, most likely in MAVSDK's library); it did not happen again, and the mission was marked failed ("Interrupted by a server restart") on the next start. The backend now prints where such a crash happens (`faulthandler`). |
| ROS 2 | Not implemented; future architecture only. |
| Flutter mobile app | Not implemented; the field view is a web page (PWA) instead. |
| Security hardening | Not implemented (rate limiting, HTTPS, security headers, token revocation, …); see `docs/ARCHITECTURE.md`. |
 
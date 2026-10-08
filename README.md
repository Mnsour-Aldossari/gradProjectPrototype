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
| `backend/app/report/` | The mission report as a PDF (fpdf2) and the search for a font with Arabic letters | `simulation/` (the survey's frame), DB models |
| `backend/app/models.py`, `db.py` | Database tables (SQLModel). Portable: SQLite by default, PostgreSQL via `DATABASE_URL` | — |
| `backend/migrations/`, `alembic.ini` | Database migrations (Alembic), run by the backend at startup | `models.py` |
| `backend/tests/` | PyTest suite | — |
| `web/` | React + TypeScript dashboard: mission planning, live satellite map, detection review and verification. Responsive, used on phones by field staff | REST/WebSocket API only |
| `scripts/` | `start_dev.cmd` (calls `start_dev.ps1`): one-click start of the backend and the web dashboard for development on Windows | `backend/`, `web/` |
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

   **One click:** double-click `scripts\start_dev.cmd`, then go to step 4. It does steps 2 and 3 for you:

   - checks that Python 3.11+ and Node.js are installed, and that ports 8000 and 5180 are free; if not, it stops with
     a message saying what to do (it never closes anything that is running);
   - the first time, creates `backend/.venv` with `requirements.txt` and installs the web packages (`npm ci`); later
     starts install again only when `backend/requirements.txt` or `web/package-lock.json` has changed;
   - opens the backend and the web dashboard in two Windows Terminal tabs, **Backend** and **Web** (two PowerShell
     windows where Windows Terminal is not installed, or with `scripts\start_dev.ps1 -PlainWindows`); the dashboard
     starts once http://localhost:8000/api/health answers;
   - opens http://localhost:5180 in the browser once the dashboard answers.

   Ctrl+C in a tab stops that server. The backend uses SQLite (`backend/uav.db`) unless `DATABASE_URL` is set in the
   terminal that runs `start_dev.cmd` (a double-click does not see a `set` made in a terminal; tried with a SQLite
   `DATABASE_URL`, not yet with PostgreSQL). Measured on Windows 11
   in a fresh copy of the repository: **44 s** the first time (installing; pip's and npm's download caches were
   already filled on that PC, so a first install on a new PC takes longer), **3 s** afterwards.

   By hand instead:

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

## Landing confirmation and sensor collection

**Landing.** A mission is **Completed** (or **Stopped**, after Return Home or Land) only when the last telemetry
shows the UAV disarmed, reported on the ground, within 0.35 m of the takeoff ground, less than 2 s old, and without
a failsafe (`backend/app/uav/landing.py`). Otherwise it is **Failed** with the reasons, e.g. "Landing not confirmed:
still armed" or "Returned home by the supervisor, but the landing was not confirmed: …". With PX4 the values come
from MAVSDK (armed, landed state, position; a failsafe from PX4's status messages); the simulator lands where the
last lane ends (0.5 m/s straight down) and then reports itself on the ground and disarmed. The landing adds a few
frames without readings; the readings, and so the demo's detections and the evaluation, are unchanged.

**Sensor collection**, shown apart from the flight: "Flight: Completed · Sensors: Partial (62%)" on the mission's
Flight card, the field view's Status tab, the 3D view's top bar, and a **Sensors** column in History
(`backend/app/api/collection.py`):

| Sensors | When |
|---|---|
| Complete (100%) | every lane read without a gap |
| Partial (n%) | a gap (more than 3 sample spacings, at least 1 m, along a lane without a reading), the survey ended early (Return Home, Land, a failed flight, a server stop), or a pause longer than 1 minute (real time) |
| Failed | the UAV flew but no reading came |
| Not started | not flown yet |
| Collecting | while it flies, with the readings so far |
| Not recorded | missions flown with v1.8 or older (their readings are counted) |

The percentage is the share of the lanes' length read without gaps; the reason and the number of readings are under
the badges. A sensor that stops sending never stops the flight: frames without a reading only leave a gap. When a
flight fails, the readings taken before are stored and counted.

## Sensor heatmap and PDF report

**Heatmap.** **Heatmap: MD / GPR / Hide** above the mission map colours the ground read so far with the metal
detector's or the radar's readings, live while the UAV flies (refreshed every 3 s) and for a finished mission (the
same page, opened from History). One row per lane, one cell per 0.5 m of lane; a cell shows the strongest reading in
it. Values are divided by a fixed full scale (MD 1.0, GPR 0.4, the same for every mission) and capped at 1; the colour
is one blue from pale (weak) to dark (strong), on a square-root scale so the soil's background still shows. The legend
says the units are normalized and the data simulated; hovering the map shows the value under the pointer. A big
survey gets fewer, bigger cells (at most 200 rows and 20,000 cells); the 60 × 40 m demo is 21 × 122 cells for its
3,293 readings (34 KB). The choice is kept per user in the browser with the other display settings (**Reset to
default** clears it). While the heatmap shows, it replaces the white band of ground scanned.

**PDF report.** **Download report** on the mission page (from the start of the survey; a report made during the flight says so) and **PDF** in History's last
column, for the supervisor only (the field operator gets 403). It holds the mission's name and dates, what flew it,
the flight status and the sensor status with its note, a map to scale (area, planned lanes, track flown, detections
with their numbers, north arrow, scale bar), a summary (potential detections per category; confirmed by team, false
alarm and awaiting verification), and a table of the adaptive detections: number, category, score, latitude,
longitude and verification. Every page ends with "Simulated data — potential detections for verification by trained
personnel" and the same in Arabic. Headings are in English and Arabic; Arabic mission names are shaped and read from
the right.

It is made on the server (`backend/app/report/`) with **fpdf2** (2.8.9, pure Python, LGPL-3.0), with **uharfbuzz**
(HarfBuzz) shaping the Arabic letters. Why there and with that:

- On the server, the server decides who may have the report, and a test can open the file and read every page. The
  same file comes out on any browser or phone, and the map is drawn from the stored data, without satellite tiles,
  so nothing is fetched from outside.
- fpdf2 installs from wheels on Python 3.14 for Windows and Linux with nothing else to set up, shapes Arabic through
  HarfBuzz and lays out right-to-left text itself. WeasyPrint (HTML to PDF) would need GTK/Pango installed on
  Windows.

No font is shipped: the report uses Arial on Windows (Segoe UI or Tahoma if Arial is missing) and DejaVu Sans on
Linux and in the Docker image, which have Arabic letters. `REPORT_FONT` (and `REPORT_FONT_BOLD`) names another .ttf
file; without a font that has Arabic letters the report answers 503 and says so.

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
| `REPORT_FONT`, `REPORT_FONT_BOLD` | unset | a .ttf font with Arabic letters (and its bold) for the PDF report; unset: Arial on Windows, DejaVu Sans on Linux |

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

The tables are created by the migrations on the first start (next section) and the demo accounts added; the database
starts empty, and the missions
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

### A hosted PostgreSQL (e.g. Neon)

Copy the connection string from the provider (Neon: **Connect**), change its start from `postgresql://` to
`postgresql+psycopg://`, and keep `sslmode=require`. In cmd, put the whole assignment in double quotes: the `&` in
the address would otherwise end the command there.

```bash
set "DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/neondb?sslmode=require&channel_binding=require"
```

The connection string holds the database password: do not paste it in chats or commit it, and reset the password
(Neon: **Reset password**) if it was shared. Each query then crosses the internet: from the PC where this was tried,
93 ms per round trip to Neon in Frankfurt, so a page takes about 0.4–0.9 s instead of a few milliseconds. A flight is
not held up by it: the backend writes the flight from a worker thread, never in the event loop that sends the live
view. Measured with PostgreSQL in Docker behind a 93 ms delay, the demo at 20× in the browser: the UAV marker moved
110 times in 12 s, at most 0.14 s apart, in even steps; before this, 8 times in 12 s, up to 1.9 s apart, jumping
ahead each time. Neon's free plan puts the database to sleep after 5 minutes without use and drops its connections;
a pooled connection unused for over 60 s is checked before it is used, so the first request after a pause does not
fail.

## Database migrations (Alembic)

The tables come from the migrations in `backend/migrations/versions/` (Alembic). The backend runs them itself at
startup (`alembic upgrade head`), on SQLite and PostgreSQL alike; there is nothing to run by hand. The first one,
`0001_baseline`, makes the tables exactly as `app/models.py` had them in v1.8.

A database made before migrations existed (a `uav.db` from v1.0 to v1.8: it has the tables but no `alembic_version`)
is handled once, at its first start: the five `missions` columns added in v1.3–v1.5 (`uav_source`, the takeoff and
landing points) are added if it lacks them, then, if it has every table and column of the baseline, it is marked as
being at `0001` and keeps all its rows. If something else is missing, the backend stops with a message naming it and
leaves the database unchanged.

Changing a table, from `backend/` (on `DATABASE_URL`, or `uav.db` when it is not set):

```bash
.venv/Scripts/python -m alembic current                                   # where the database is
.venv/Scripts/python -m alembic revision --autogenerate -m "what changed"  # after editing app/models.py
```

Read the new file in `migrations/versions/` before committing it (on SQLite, Alembic copies a table to change its
columns: `render_as_batch`). The next start of the backend applies it.

## Tests and type check

```bash
cd backend
.venv/Scripts/python -m pytest
```

Expected result: **240 passed, 1 skipped, 2 xfailed** with `requirements-px4.txt` installed (the skipped one runs
only on PostgreSQL, with `TEST_DATABASE_URL` set: **241 passed, 2 xfailed**; without MAVSDK two PX4 tests are skipped
too, and without a `backend/uav.db` the test that upgrades a copy of it is skipped). This includes the mandatory tests T1–T3 on the evaluation seeds. The
two expected failures are a known limitation, marked `xfail(strict=True)` (see `docs/EVALUATION_PROTOCOL.md`
section 6): `test_lone_low_metal_mine_is_reported_through_radar` fails for seeds 502 and 503; seed 501 runs as a
normal test.

```bash
cd web
npm run typecheck
npm test
```

`npm test` runs the web tests (Vitest, Testing Library, jsdom): **15 passed**, in about 3 s. They render the app
without a backend: `fetch` and the WebSocket are faked (`web/src/test/fakes.tsx`), and the Leaflet map is replaced by
a plain element that shows where the UAV is and which detections it was given (`web/src/test/setup.ts`). They cover
signing in (each role lands on its own page, a wrong password, a field operator sent away from a supervisor page),
planning a mission (each drawn outline is checked with `POST /api/missions/check` and its problems shown), the flight
controls (Pause and Resume; Return Home and Land ask first; hidden from the field operator), live updates (telemetry
moves the UAV, a new detection joins the list and the map), verification (`PATCH` with `confirmed_by_team` or
`false_alarm` and the notes), and display settings (theme and text size saved per user and restored). The real map,
drawing on it, and the 3D view are not covered (jsdom has no layout or WebGL). On Node.js 25 and newer, Node's own
`localStorage` hides jsdom's; `web/vitest.config.ts` turns it off in the test workers
(`--no-experimental-webstorage`), so `npm test` works the same on every platform.

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
(supervisor and field operator, re-created by the same seeding the server runs at startup). It drops every table,
`alembic_version` too, and runs the migrations again. Stop the backend before running it. `backups/` is git-ignored.
It only touches the database in `DATABASE_URL`; the automatic backup is made for SQLite only. (`--yes` was tried on a
PostgreSQL in Docker and runs in the tests; not run on `uav.db` while this README was reviewed.)

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
| GET | `/api/missions/{id}/heatmap` | any user — the readings so far as a grid of normalized peaks, one row per lane (simulated data) |
| GET | `/api/missions/{id}/report.pdf` | supervisor — the mission report as a PDF; 503 if the server has no font with Arabic letters |
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
- Landing confirmation and sensor collection: tested with PyTest (each landing check, gaps, a sensor dropping out
  mid-lane, no readings, a flight failing mid-survey, a server stop, a pause over a minute, migration `0002` on old
  databases) and in the browser with the simulator (desktop and phone size, light and dark: the demo ended Completed
  with Sensors Complete (100%) and the same detections as before; Land after 8 s gave Stopped, Partial (12%); a 65 s
  pause gave Completed, Partial). With PX4 SITL (headless Docker image) on a 21 × 21 m survey: flown to the end,
  Completed with the landing confirmed from MAVSDK and Sensors Complete (100%, 856 readings); Land after 75 s gave
  Stopped, Partial (36%). Not tried: a real PX4 failsafe (the reason is taken from PX4's status messages mentioning
  "failsafe"), Gazebo's window.
- Sensor heatmap: tested with PyTest (lanes as rows, strongest reading per cell, the full scale, fewer cells for a big
  survey) and in the browser on the demo with the simulator, at desktop and phone size, light and dark: it filled in
  lane by lane during the flight, MD and GPR and Hide switch it, the value shows on hover, and the choice stayed after
  a reload.
- PDF report: tested with PyTest on SQLite and PostgreSQL (a valid PDF for the supervisor with the notice in English
  and Arabic and "Page n of m" on every page, the detections' coordinates and scores, an Arabic mission name, 80
  detections over several pages; 403 for the field operator, 401 without a token, 503 without a font). In the browser
  the mission page's and History's buttons fetched the PDF (the file was not saved), the field operator had no
  button, and the report came out for each of the 59 missions in a copy of the development PC's database (simulator
  and PX4, completed, stopped and failed; at most 0.35 s each). Opened and looked at: the demo's, an Arabic-named
  mission's and a failed PX4 flight's.
- Fixed-threshold baseline and adaptive classification, calibrated on tuning seeds and evaluated on separate seeds.
- FastAPI backend with SQLite, login with supervisor / field-operator roles, live WebSocket updates.
- Database migrations (Alembic), run at startup: tried on SQLite and on PostgreSQL 17 in Docker with a new database,
  a database as v1.2 and v1.8 left it, and a copy of the development PC's `uav.db` (58 missions, 115,030 telemetry
  points, 111,226 readings, 400 detections: every row kept, the missions listed by the API afterwards), and in the
  backend's Docker image. Not tried: Neon. Migration `0002` (sensor collection) was tested with PyTest on SQLite and PostgreSQL and run on a copy of the development PC's `uav.db`.
- Web tests (`npm test` in `web/`, 15 tests, Node.js 26 on Windows 11): sign-in, mission planning, flight controls,
  live updates, verification and display settings, with the backend faked. Of six deliberate breakages of the code
  they cover, five made a test fail; the sixth changed nothing a user sees (field operators are sent from `/` to
  `/field` as well).
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
- One-click start `scripts\start_dev.cmd` (Windows 11, Windows PowerShell 5.1): tried in a fresh copy of the
  repository in a folder whose path has a space, with Windows Terminal tabs and with plain PowerShell windows; a
  second start installed nothing, a changed `requirements.txt` was installed again, the Web tab waited for the
  backend, `DATABASE_URL` reached the backend, and it refused to start with port 8000 or 5180 in use (also IPv6
  only) and named what was missing with Python or Node.js taken off `PATH` (also with only the Microsoft Store's
  `python` shortcut). Not tried: a PC that never had Python or Node.js installed, another Windows version, PowerShell 7.

Not working, not run, or only partly checked:

| Item | Status |
|---|---|
| Docker | `docker-compose.yml`, `backend/Dockerfile`, `web/Dockerfile`, `web/nginx.conf`: the images were built and the containers run with `docker compose up --build -d` (Docker Desktop, Windows 11), also with `docker-compose.postgres.yml`; on http://localhost:8080 `/api/health` answered ok, signing in worked and the demo scenario ran to the end with its data stored (on PostgreSQL), and the data survived a restart of the backend container. Not tried: a hosted deployment of the containers. |
| Postman | `postman/uav-prototype.postman_collection.json` (six requests) **has not been opened in Postman**. The same requests and test scripts were replayed against the running backend with a small Node script that mimics `pm`, and all passed. |
| PWA install | The web app manifest and icons were checked in the browser. The service worker (`web/public/sw.js`, network-first, never caches `/api` or `/ws`) could not be registered in the built-in test browser, and installing on a real phone has not been tried. |
| PostgreSQL | Run against PostgreSQL 17 in Docker: all tests pass on it (`TEST_DATABASE_URL`), a database from an older version gets its new columns, a demo mission, verification, history and evaluation work, and the data survives a restart. A hosted PostgreSQL (Neon's free plan, Frankfurt) was used from the development PC: it worked, but during flights the UAV froze on the page and then jumped ahead. That was fixed (the flight is written from a worker thread) and measured with PostgreSQL in Docker behind the same 93 ms delay; not yet tried again on Neon itself. Not tried: PostGIS, a large amount of data, and moving the missions of an existing `uav.db` over. |
| PX4 SITL + Gazebo | Flown only on small surveys, in the headless Docker image and in Gazebo's window (WSL, one PC); not tried on the full demo field or with a real vehicle. QGroundControl, started by hand, followed the flights from PX4 SITL (not through the app). MD/GPR come from the project's sensor model at PX4's position, not from Gazebo sensors. MAVSDK's mission progress came back empty with PX4 1.17, so the waypoint being flown is taken from PX4's position. Once (1 of the 6 test flights of the Gazebo window, never before in this project) the backend stopped right after a landing with a crash in native code (exit code 139, most likely in MAVSDK's library); it did not happen again, and the mission was marked failed ("Interrupted by a server restart") on the next start. The backend now prints where such a crash happens (`faulthandler`). |
| ROS 2 | Not implemented; future architecture only. |
| Flutter mobile app | Not implemented; the field view is a web page (PWA) instead. |
| Security hardening | Not implemented (rate limiting, HTTPS, security headers, token revocation, …); see `docs/ARCHITECTURE.md`. |
 
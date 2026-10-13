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
| `ros2_ws/` | ROS 2 Jazzy packages: messages (`uav_landmine_interfaces`), the mission bridge, the detector node, mission control and the PX4 reader (`uav_landmine_ros`), `build.sh` and `env.sh` | the backend's REST API, `backend/app/detection`, PX4's uXRCE-DDS (`px4_msgs`) |
| `backend/app/models.py`, `db.py` | Database tables (SQLModel). Portable: SQLite by default, PostgreSQL via `DATABASE_URL` | — |
| `backend/migrations/`, `alembic.ini` | Database migrations (Alembic), run by the backend at startup | `models.py` |
| `backend/tests/` | PyTest suite | — |
| `web/` | React + TypeScript dashboard: mission planning, live satellite map, detection review and verification. Responsive, used on phones by field staff | REST/WebSocket API only |
| `scripts/` | `start_dev.cmd` (calls `start_dev.ps1`): one-click start of the backend and the web dashboard for development on Windows | `backend/`, `web/` |
| `docs/` | `ARCHITECTURE.md` (report section 4.1, diagrams, future phases, security notes), `DEMO_SCRIPT.md` (Arabic demo script), `EVALUATION_PROTOCOL.md` (seeds, calibration), `EVALUATION_RESULTS.md` (generated results), `calibration_result.json`; the same three with `_V2`/`_v2` for detector version 2, and `evaluation_v2.json` | — |

Data flow: `simulation` → `uav.SimulatedSource` (MAVLink-shaped frames), or PX4 → `uav.Px4MavlinkSource` → `api.runner` → database + `detection.live_detector` (detector version 2, every 5 s of flight) → WebSocket events → web.

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

## Expected accuracy while planning

**Plan a mission** shows, under the height, speed and lane spacing, what the detector is expected to find with those
settings on the chosen soil: the share of the mines found (with its margin), the share of the reports that are
mines, the share of the low-metal mines found, and false alarms per hectare. It follows every change.

The numbers come from `backend/app/detection/accuracy_table.json`, which `python -m scripts.accuracy_table` (in
`backend/`) builds: the standard test field flown on a grid (height 0.5–5 m, speed 0.5–5 m/s, lane spacing 0.5–5 m,
630 settings with the soils) on 30 seeds of its own (3000–3029, neither tuning nor evaluation seeds), scored as the
evaluation scores (a mine within 1.5 m reported as high priority or needs verification). Between grid points the
counts are interpolated. About 13 minutes on 18 cores; it does not touch `docs/` or the frozen parameters.
`GET /api/accuracy` gives one estimate, `GET /api/accuracy/grid` a whole soil.

What the table shows (simulated data, the app's detector, version 2 since 2026-10-08; the table was built again for it):

| Soil | Standard: 1.5 m, 2 m/s, 2 m lanes | Slower, closer lanes: 1.5 m, 1 m/s, 1 m lanes | Lower too: 1.0 m, 1 m/s, 1 m |
|---|---|---|---|
| Dry sand | 84 % found, 69 % of low-metal | 96 %, 91 % | 99 %, 98 % |
| Wet clay | 63 %, 62 % | 78 %, 88 % | 83 %, 94 % |
| Mineralised rocky | 74 %, 41 % | 90 %, 76 % | 91 %, 79 % |

Slower flight and closer lanes help everywhere (the flight takes about four times longer), and with version 2 flying
lower helps too. With version 1 it did not: version 1 lost metal mines below 1.5 m (in rocky soil 70 % at 1.0 m against
86 % at 1.5 m with the same speed and lanes), which led to version 2. The estimate compares settings inside the simulation; it does not predict field performance.

**The Sensors page** (menu: **Sensors**, every user) explains it all in English or Arabic (a button switches; the
choice stays in the browser): what the metal detector and the radar sense and where each is weak, the five steps
from readings to a potential detection, the official evaluation's accuracy per soil (from `/api/evaluation`), the
same estimate with sliders for height, speed and lane spacing (with the flight time per hectare, each sensor's
signal against 1.5 m, and a chart of mines found by speed for 1, 2 and 3 m lanes), and what it cannot do yet.

## Detector version 2 (adopted by the owner's decision)

The accuracy table showed that the adaptive detector loses metal mines when flown lower: its body-ratio rule was
calibrated at 1.5 m. Version 2 (`backend/app/detection/adaptive_v2.py`) corrects that ratio for the sensor height and
calls a reflector without metal deeper than 0.12 m a stone; a matched filter along the track was tried and not
chosen. Version 1, its parameters and its results are unchanged.

It was calibrated on the tuning seeds only, at five survey settings, for the most mines found with no more false
alarms than version 1 (`scripts/calibrate_v2.py`). Its protocol (`docs/EVALUATION_PROTOCOL_V2.md`), committed with
the frozen parameters before the run, fixed fresh evaluation seeds (4000–4029, 450 surveys) and an adoption rule:
pooled over the five settings, at least 0.02 more recall and no more false alarms; at the standard setting, recall at
most 0.02 lower. Run once (`scripts/evaluate_v2.py`, `docs/EVALUATION_RESULTS_V2.md`):

| | Version 1 | Version 2 |
|---|---|---|
| Mines found, five settings pooled | 996 of 1370 (72.7 %) | 1130 (82.5 %) |
| False alarms, five settings pooled | 401 | 407 |
| Mines found at the standard setting | 71.9 % | 78.1 % |
| Mines found at 0.75 m | 53.3 % | 79.2 % |
| Low-metal mines found, pooled | 493 of 745 | 557 |

Version 2 found more mines at every setting, but raised 6 more false alarms than version 1 over the 450 surveys, so
the second condition failed: under the rule, version 1 would have stayed. **After seeing these results the project
owner chose to adopt version 2 anyway**, judging a missed mine worse than a few false alarms. So the app (live
detection while a mission flies) and the ROS 2 detector node run version 2 (`detect_live` / `live_detector` in
`app/detection/__init__.py`). This is the owner's decision, not a pass of the rule; the rule, the parameters and the
numbers were not changed after the run. Version 1 stays the officially evaluated detector (`docs/EVALUATION_RESULTS.md`,
the Evaluation page). Simulated data.

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

## ROS 2 (optional)

`ros2_ws/` holds two ROS 2 Jazzy packages that run beside the backend; the backend still flies the mission (simulator
or PX4) and stores it as before.

- `uav_landmine_interfaces`: the messages `SensorReading`, `MissionInfo`, `Detection`, `DetectionArray` and
  `Px4Status`, the services `StartMission` and `ControlMission`, and the action `FlySurvey`.
- `uav_landmine_ros`:
  - **mission_bridge** follows a mission in the backend (the next one that flies, or `mission_id:=N`, flying or
    already flown) and publishes it. Every reading goes out, in the order it was taken, paged from
    `GET /api/missions/{id}/readings`.
  - **landmine_detector** is the backend's live detector (version 2) as a node (`backend/app/detection`, unchanged). It takes
    the readings, publishes its potential detections every 25 readings, and once more, final, when the mission has
    ended. A real sensor publishing `SensorReading` messages could feed it the same way.
  - **compare_with_backend** waits for the detector node's final result and compares it with what the backend
    stored (category, number of readings, score, position); exit code 0 when they agree.

| Topic | Message | What |
|---|---|---|
| `/mission/info` | `MissionInfo` | the mission, its status and how many readings were sent (kept for late subscribers) |
| `/sensors/readings` | `SensorReading` | every MD/GPR reading, in the "survey" frame (metres from the area's centre, x east, y north) |
| `/uav/fix`, `/uav/pose`, `/uav/path`, `/uav/battery` | `NavSatFix`, `PoseStamped`, `Path`, `BatteryState` | the UAV |
| `/landmine/detections` | `DetectionArray` | the backend's adaptive detections, with their verification |
| `/landmine/candidates` | `DetectionArray` | the detector node's |
| `/landmine/markers` | `MarkerArray` | area, readings and both sets of detections, for RViz |
| `/tf`, `/tf_static` | transforms | `map` → `survey` (the same place) → `uav` (where the UAV is and where it heads) |
| `/diagnostics` | `DiagnosticArray` | the bridge (can it read the backend, the mission, readings sent) and the detector (readings received, missing, final) |

**From the dashboard.** The supervisor's menu has a **ROS 2** switch (on Windows with WSL): it starts the nodes in
WSL Ubuntu 24.04 (`ROS_WSL_DISTRO`), with PX4's link too where `build.sh` built it (`px4.launch.py landmine:=true`,
else `landmine.launch.py`), and stops them again (Ctrl+C for the launch). The nodes get a token of the supervisor who
pressed it (valid 12 hours, as a sign-in), never a password, so nothing is typed; it is fed to bash in WSL, not put
on a command line. The dot is green while they run. It refuses to start a second set while ROS 2 runs from a WSL
terminal, and says why when it cannot start (e.g. `build.sh` not run yet). The commands below do the same by hand.

Run it in the WSL Ubuntu 24.04 that has ROS 2 Jazzy (the backend on Windows is reached at `http://127.0.0.1:8000`
through WSL's mirrored networking):

```bash
bash /mnt/c/Users/Admin/Desktop/uav-landmine-prototype/ros2_ws/build.sh
source /mnt/c/Users/Admin/Desktop/uav-landmine-prototype/ros2_ws/env.sh
export UAV_USERNAME=field UAV_PASSWORD='<the field password in backend/app/seed.py>'
ros2 launch uav_landmine_ros landmine.launch.py
```

Then start a survey in the dashboard. In another WSL terminal, after `source .../ros2_ws/env.sh`:
`ros2 topic echo /landmine/candidates`, `ros2 topic echo /diagnostics`, `ros2 run tf2_ros tf2_echo survey uav`,
`ros2 param describe --no-daemon /mission_bridge poll_period_s`, or
`ros2 run uav_landmine_ros compare_with_backend --ros-args -p mission_id:=<id>`. The workspace is
`~/uav_landmine_ws`, apart from any other ROS workspace on the PC. (The `ros2` commands that ask the ROS daemon timed
out on this PC; `--no-daemon` avoids it.)

**Commands from ROS.** `mission_control` (started by the same launch file) takes commands and passes them to the
backend's API with a supervisor's account, `UAV_CONTROL_USERNAME` and `UAV_CONTROL_PASSWORD`; the backend refuses
the field operator's (403). The backend then flies the mission as when the dashboard's buttons are used, so the
landing check, the sensor collection and the dashboard stay right:

| Name | Type | What |
|---|---|---|
| `/mission/start` | service `StartMission` | start a planned mission (simulator or PX4, Gazebo's window or not), or the demo scenario (`mission_id: 0`) |
| `/mission/control` | service `ControlMission` | pause, resume, return or land (`mission_id: 0`: the mission flying) |
| `/mission/fly` | action `FlySurvey` | start a mission and follow it to its end, with feedback (status, phase, progress, readings, detections); cancelling it lands the UAV (or returns, `cancel_action: return`) |

```bash
export UAV_CONTROL_USERNAME=supervisor UAV_CONTROL_PASSWORD='<the supervisor password in backend/app/seed.py>'
ros2 action send_goal --feedback /mission/fly uav_landmine_interfaces/action/FlySurvey "{mission_id: 0, speed_factor: 10}"
ros2 service call /mission/control uav_landmine_interfaces/srv/ControlMission "{mission_id: 0, action: pause}"
```

**Settings.** `config/params.yaml` holds every setting of the nodes; `params_file:=<your file>` uses another one, and
`backend_url:=` and `mission_id:=` override those two.

**Recording and replay.** `ros2 launch uav_landmine_ros landmine.launch.py record:=true` also records the topics
(MCAP) in `~/uav_bags/mission_<date>_<time>`; Ctrl+C closes the recording. A recording plays back to the detector
node alone, without the backend, which then compares its result with the backend's detections in the recording:

```bash
ros2 launch uav_landmine_ros replay.launch.py bag:=$HOME/uav_bags/<folder> rate:=5
```

**Fast DDS over shared memory.** On the development PC Fast DDS's UDP path delivered nothing between two processes
(not even ROS's minimal publisher and subscriber), while shared memory did. `config/fastdds_shm.xml` selects shared
memory only; `landmine.launch.py` and `env.sh` use it unless `FASTRTPS_DEFAULT_PROFILES_FILE` is set. So nodes in
another WSL distribution or on another machine cannot join.

**PX4 read directly.** For a mission flown with PX4, ROS can also read PX4 itself, over uXRCE-DDS (PX4's
`uxrce_dds_client`, started by PX4 v1.17's SITL on UDP port 8888, and the Micro XRCE-DDS Agent), next to the backend's
MAVLink link. It only reads: the backend still flies the mission and is the only one that commands PX4 (ROS's commands
go through it, as above). `build.sh` also builds PX4's messages (`px4_msgs` at v1.17.0, PX4's version) and the agent
(v2.4.3) when their sources are in `~/dev/upstream` (or `UAV_PX4_MSGS_SRC`, `UAV_XRCE_AGENT_SRC`); the sources are
linked, not changed. `px4_link` publishes:

| Topic | Message | What |
|---|---|---|
| `/px4/fix` | `NavSatFix` | PX4's global position (`/fmu/out/vehicle_global_position`), up to 50 a second |
| `/px4/status` | `Px4Status` | armed, on the ground (PX4's land detector), mode (`auto_mission`, `auto_rtl`, `auto_land`…), failsafe, battery |
| `/px4/battery` | `BatteryState` | |
| `/diagnostics` | `DiagnosticArray` | "PX4": is PX4 heard; "PX4 vs backend": metres between PX4's position and the backend's latest (MAVLink), measured to the track PX4 flew over the last 10 s since the backend's arrives a little later, and whether both say the UAV is flying or down. A warning above 1 m or when they disagree |

```bash
# PX4 in Gazebo's window from the same Ubuntu: the backend started with PX4_GAZEBO_DISTRO=Ubuntu-24.04 and
# PX4_GAZEBO_DIR=<PX4-Autopilot's folder in that Ubuntu's home>, then a PX4 mission started with Gazebo's window
ros2 launch uav_landmine_ros px4.launch.py                  # the agent and px4_link
ros2 launch uav_landmine_ros px4.launch.py landmine:=true   # and the bridge, the detector and mission control
```

The agent must run in the same Ubuntu as the nodes (shared memory, below). The participant PX4 asks the agent for is
built from PX4's own XML, which leaves out the shared-memory profile, so `px4.launch.py` gives the agent
`FASTDDS_BUILTIN_TRANSPORTS=SHM` (`agent_transports:=DEFAULT` where UDP works). The agent's console log is off in this
build (Ubuntu 24.04's spdlog cannot build v2.4.3's log lines). PX4 v1.16 and later add the version to some topics
(`vehicle_status_v1`, `battery_status_v1`); `status_topic` and `battery_topic` in `config/params.yaml` name them.
PX4 in the headless Docker image is not read this way: its `uxrce_dds_client` sends to 127.0.0.1 inside its
container, where no agent runs.

**RViz.** `rviz/landmine.rviz` and `rviz:=true` are there, but RViz is not installed in that Ubuntu
(`sudo apt install ros-jazzy-rviz2`), so they were not tried.

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
| `SECRET_KEY_FILE` | `backend/.secret_key` | where the generated signing key is kept; the Docker image sets `/data/.secret_key`, on the data volume, so sessions survive a rebuild |
| `CORS_ORIGINS` | `http://localhost:5180,http://127.0.0.1:5180` | page addresses (comma-separated) allowed to call the API from a browser; only `GET POST PUT PATCH DELETE` and the `Authorization` / `Content-Type` headers are allowed |
| `SEED_DEMO_USERS` | `1` | `0`: create no demo accounts (use this on anything but a local trial) |
| `SEED_SUPERVISOR_PASSWORD`, `SEED_FIELD_PASSWORD` | the demo passwords below | replace the demo passwords when the accounts are created; an account that already exists keeps its password |
| `PX4_MANAGE_DOCKER` | `1` | `0`: never start or restart PX4 SITL at a mission's takeoff point, neither the Docker container nor Gazebo's window in WSL (each is off anyway without the `docker` / `wsl` command) |
| `PX4_GAZEBO_DISTRO` | `Ubuntu-22.04` | the WSL distribution where PX4-Autopilot is built, for **PX4 SITL + Gazebo window** |
| `PX4_GAZEBO_DIR` | `PX4-Autopilot` | PX4-Autopilot's folder in that distribution, in the user's home or an absolute path |
| `ROS_WSL_DISTRO` | `Ubuntu-24.04` | the WSL distribution where `ros2_ws/build.sh` built the ROS 2 nodes, for the dashboard's **ROS 2** switch |
| `ROS_BACKEND_URL` | empty | where those nodes reach the backend; empty: `http://127.0.0.1:<this backend's port>` |
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
-f docker-compose.postgres.yml up --build -d` (the database has no published port; `POSTGRES_PASSWORD` has no
default: set it in the shell or a `.env` file first). The backend container now runs as a non-root user (`uav`): a
`/data` volume made by an earlier version is owned by root, so remove it (`docker compose down -v`, which deletes its
data) or `chown 10001 /data` in it before starting. Login attempts are limited per client address and username (5
failures a minute, then `429`), and the web container sends a Content-Security-Policy and other security headers.

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

Expected result: **281 passed, 1 skipped, 2 xfailed** with `requirements-px4.txt` installed (the skipped one runs
only on PostgreSQL, with `TEST_DATABASE_URL` set: **282 passed, 2 xfailed** (with detector version 2 live; in 6 full runs the ground truth's end-to-end test failed twice and passed alone 4 times out of 4, so it is still intermittent on PostgreSQL; before it, 8 full runs; one earlier run had the ground truth's end-to-end test fail once, which did not come back in about 20 more runs, also with the CPU busy; if it does, the test now names the part that differs); without MAVSDK two PX4 tests are skipped
too, and without a `backend/uav.db` the test that upgrades a copy of it is skipped). This includes the mandatory tests T1–T3 on the evaluation seeds. The
two expected failures are a known limitation, marked `xfail(strict=True)` (see `docs/EVALUATION_PROTOCOL.md`
section 6): `test_lone_low_metal_mine_is_reported_through_radar` fails for seeds 502 and 503; seed 501 runs as a
normal test.

```bash
cd web
npm run typecheck
npm test
```

`npm test` runs the web tests (Vitest, Testing Library, jsdom): **21 passed**, in about 3 s. They render the app
without a backend: `fetch` and the WebSocket are faked (`web/src/test/fakes.tsx`), and the Leaflet map is replaced by
a plain element that shows where the UAV is and which detections it was given (`web/src/test/setup.ts`). They cover
signing in (each role lands on its own page, a wrong password, a field operator sent away from a supervisor page),
planning a mission (each drawn outline is checked with `POST /api/missions/check` and its problems shown), the flight
controls (Pause and Resume; Return Home and Land ask first; hidden from the field operator), live updates (telemetry
moves the UAV, a new detection joins the list and the map), verification (`PATCH` with `confirmed_by_team` or
`false_alarm` and the notes), display settings (theme and text size saved per user and restored), the expected accuracy while planning, the
Sensors page (both languages, the estimate following the soil), and the menu's ROS 2 switch (on, off, the reason
it did not start; not for the field operator). The real map,
drawing on it, and the 3D view are not covered (jsdom has no layout or WebGL). On Node.js 25 and newer, Node's own
`localStorage` hides jsdom's; `web/vitest.config.ts` turns it off in the test workers
(`--no-experimental-webstorage`), so `npm test` works the same on every platform.

### The ground truth stays in the simulator

The simulator knows what is buried where (kind, position, depth, metal content) and the soil model behind the
readings, and uses them only to make the MD and GPR readings. `backend/tests/test_ground_truth_isolation.py` checks
that nothing after the readings uses them:

- **The detectors cannot reach it:** the modules in `app/detection/` import only each other and the standard
  library. `detection/evaluation.py`, which scores detections against the truth after they are made, is left out;
  the mission runner and the PX4 source never import it.
- **Other labels, same numbers, same results:** every buried object gets another kind (two kinds stop or start
  being a mine) and keeps its numbers. The readings and the detections stay exactly the same: offline for the three
  soil types, over PX4's positions, and through a whole mission run (every column of the stored readings and
  detections, the REST responses and the WebSocket snapshot).
- **No ground-truth names in what the API sends or stores:** `kind`, `is_target`, `depth_m`, `metal_mass`, the soil's
  moisture and noise, `truth`, `target`, `mine`, `buried` and the like, also inside a longer name, appear at no depth
  in the REST responses, the live WebSocket events, the OpenAPI document or the database tables. `est_depth_m`, the
  detector's estimate from the radar, is allowed.
- `/api/evaluation` is the offline evaluation on the evaluation seeds, so it names the kinds of object, by design: as
  counts per soil type, with no positions.

The tests were shown to catch deliberate leaks (8 tried: the sensor model reading the label, a detector importing
the simulator or the scorer, the label mixed into the readings or written into the explanation by the runner, a
`buried_kind` field, a `targets_left` event field, a `true_depth_m` column), then the code was put back.

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
| POST | `/api/missions/check` | supervisor; the same body as creating a mission; returns the lanes and the problems for that outline, and the expected accuracy with its settings, without storing anything |
| PUT | `/api/missions/{id}/takeoff` | supervisor; body `{"lat": …, "lon": …}` (or `{}` for the default, 5 m outside the survey start) on a planned mission; 422 if over 900 m from the survey start |
| PUT | `/api/missions/{id}/landing` | supervisor; the same body (or `{}`: land at the takeoff point); 422 if over 900 m from the survey end |
| POST | `/api/missions/{id}/control` | supervisor; body `{"action": "pause" \| "resume" \| "return" \| "land"}` during a flight; 409 if the mission is not flying or the command does not apply now |
| POST | `/api/missions/demo` | supervisor — creates and starts the fixed demo scenario (seed 2000, dry sand, 20×) |
| GET | `/api/missions/{id}/telemetry` | any user |
| GET | `/api/missions/{id}/readings?after_id=0&limit=5000` | any user — the sensor readings in the order they were taken, with their place in metres from the survey area's centre (for the ROS 2 bridge) |
| GET | `/api/accuracy?soil_type=&altitude_m=&speed_mps=&line_spacing_m=` | any user — the detector's expected accuracy with those settings (simulated); `/api/accuracy/grid?soil_type=` every grid point of a soil |
| GET | `/api/ros` | supervisor — can this backend start ROS 2 (Windows with WSL), and does it run |
| POST | `/api/ros/start`, `/api/ros/stop` | supervisor — start or stop the ROS 2 nodes in WSL (the menu's **ROS 2** switch); 502 with the reason when WSL cannot |
| GET | `/api/missions/{id}/detections?method=adaptive` | any user |
| GET | `/api/missions/{id}/profile` | any user — how the live detector (version 2) is configured for the mission |
| GET | `/api/missions/{id}/heatmap` | any user — the readings so far as a grid of normalized peaks, one row per lane (simulated data) |
| GET | `/api/missions/{id}/report.pdf` | supervisor — the mission report as a PDF; 503 if the server has no font with Arabic letters |
| WS | `/ws/missions/{id}` (first message `{"type":"auth","token":"..."}`; `?token=` still accepted) | snapshot, then live telemetry, detections, alerts, status |
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
- Adaptive detection version 2 (`backend/app/detection/adaptive_v2.py`), used by the app and the ROS 2 detector node
  since 2026-10-08 by the owner's decision, although it did not meet one condition of its adoption rule: see
  **Detector version 2**. Version 1 stays the officially evaluated detector.
- ROS 2 (Jazzy, WSL Ubuntu 24.04): `colcon test` (22 tests: the survey frame is the backend's, the detector fed one
  reading at a time finds what the backend's finds on two soils, the messages, transforms and diagnostics, the
  commands against a fake backend, PX4's modes and the PX4-versus-backend check; since version 2 the node is compared
  with version 2) and end to end against the backend on Windows (these runs were with detector version 1, before
  version 2): the demo flown live, two finished
  missions replayed, and a wet-clay survey landed early (1,009 readings); each time the detector node's potential
  detections were the backend's (9, 9, 9 and 1). Ctrl+C stops both nodes cleanly. Also tried: the UAV's transform
  (`tf2_echo survey uav`), `/diagnostics`, the parameters and their descriptions, a recording of a mission (3,293
  readings) closed by Ctrl+C, and its replay to the detector alone: the same 9 potential detections as the backend's,
  in 3 s at 5× speed. Commands from ROS: the demo started with `/mission/fly` (feedback each second), paused, resumed
  and landed with `/mission/control`: stopped, sensors partial (14%), as the dashboard showed; cancelling
  `/mission/fly` landed the UAV (goal cancelled, mission stopped); the field operator's account, an unknown command, a
  command with no mission flying and the demo with PX4 were refused with the reason.
  PX4 read directly: a survey flown by PX4 v1.17 in Gazebo's window (WSL Ubuntu 24.04), started and landed early
  through `/mission/start` and `/mission/control`; `px4_link` got PX4's position about 50 times a second over
  uXRCE-DDS, within 0.02 m of the backend's MAVLink position all the way, and both said flying, then down after the
  landing (PX4's land detector and the backend's stopped mission). Ctrl+C stops the nodes cleanly (the agent, a
  native program, ends by the signal, which launch reports as exit code -2). The headless Docker image's PX4 does not
  reach the agent: its `uxrce_dds_client` sends to 127.0.0.1 inside the container. The dashboard's ROS 2 switch, in
  the browser: on started the nodes with PX4's link in WSL, which followed the demo flown next with the supervisor's
  token (850 readings by the first look); off stopped them cleanly; with ROS 2 already running from a WSL terminal it
  refused and said so.
- The ground truth stays in the simulator: the detectors, the stored data and the API do not use or give it (tested
  with PyTest on SQLite and PostgreSQL; see "The ground truth stays in the simulator").
- FastAPI backend with SQLite, login with supervisor / field-operator roles, live WebSocket updates.
- Database migrations (Alembic), run at startup: tried on SQLite and on PostgreSQL 17 in Docker with a new database,
  a database as v1.2 and v1.8 left it, and a copy of the development PC's `uav.db` (58 missions, 115,030 telemetry
  points, 111,226 readings, 400 detections: every row kept, the missions listed by the API afterwards), and in the
  backend's Docker image. On Neon the app was used (see PostgreSQL in the "Not working, not run, or only partly checked" table), but these
  migrations were not run there. Migration `0002` (sensor collection) was tested with PyTest on SQLite and PostgreSQL and run on a copy of the development PC's `uav.db`.
- Web tests (`npm test` in `web/`, 21 tests, Node.js 26 on Windows 11): sign-in, mission planning, flight controls,
  live updates, verification, display settings, the accuracy estimate, the Sensors page and the ROS 2 switch, with the
  backend faked. The first 15 of them were checked against deliberate breakages: of six breakages of the code
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
| Scenario seed | With a mission's scenario seed and this code the buried objects of a simulated mission can be rebuilt, so the API gives it to the supervisor only (the field operator gets `null`; tested with PyTest). The supervisor still sees and chooses it, which keeps the demo and the tests repeatable. Still visible to anyone: the demo mission's name, "Demo scenario (seed 2000, dry sand)". The detectors never use the seed. |
| ROS 2 | The bridge, the detector node, recording and replay, commands through the backend, and PX4 read directly over uXRCE-DDS (Gazebo's window in WSL) work (see **ROS 2**). Not working: PX4 in the headless Docker image does not reach the agent (it sends to its own container). Not tried: RViz (not installed), a real vehicle, ROS 2 Humble, nodes on another machine (shared memory only). ROS never commands PX4 directly; the backend does. |
| Flutter mobile app | Not implemented; the field view is a web page (PWA) instead. |
| Security hardening | Not implemented (rate limiting, HTTPS, security headers, token revocation, …); see `docs/ARCHITECTURE.md`. |
 

## Acknowledgements

The ROS 2 side and the metal-detector and radar sensors started from **Osama**'s work: the basic idea of both, and
some of their features, come from Osama's prototype. The PX4 link was also built and tested with Osama's setup in
WSL (PX4-Autopilot v1.17.0 built for SITL with Gazebo, `px4_msgs` and the Micro XRCE-DDS Agent), which this project
links to and builds on without changing it. The implementation in this repository (the backend, the detectors, the
ROS 2 packages and the web app) was written for this project.

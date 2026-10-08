"""The ground truth (what is buried where) stays inside the simulator.

The sensor model needs the buried objects to make the MD and GPR readings; nothing after the readings may use
them. Checked three ways: the detection modules cannot import it, objects with other labels and the same numbers
give the same readings and detections (offline, over PX4's positions and through a whole mission run), and no name
from the ground truth appears at any depth in what the API sends (REST, OpenAPI, the WebSocket) or stores.
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path

import pytest
from conftest import auth_headers, mission_body, wait_until_finished
from sqlmodel import Session, SQLModel, select

import app.detection
from app.detection import SurveyContext, detect_adaptive, detect_baseline
from app.detection.evaluation import TruthObject
from app.detection.types import Reading
from app.evaluation.protocol import EVALUATION_SEEDS, STANDARD_SURVEY
from app.models import Detection, SensorReading
from app.seed import DEMO_USERS
from app.simulation import ObjectKind, Scenario, Simulation, SimulationConfig, SoilProfile, build_simulation
from app.simulation.scenario import BuriedObject
from app.simulation.sensors import SensorModel
from app.uav import simulated_source
from app.uav.px4_plan import PathProgress, Px4State, build_frame

# Every object gets another kind and keeps its numbers: two of the four kinds stop or start being mines.
RELABEL = {
    ObjectKind.METAL_MINE: ObjectKind.SCRAP_METAL,
    ObjectKind.SCRAP_METAL: ObjectKind.ROCK,
    ObjectKind.ROCK: ObjectKind.LOW_METAL_MINE,
    ObjectKind.LOW_METAL_MINE: ObjectKind.METAL_MINE,
}

# The fields of the ground truth (BuriedObject, Scenario, SoilProfile and the evaluator's TruthObject) and the
# evaluator's words for it. The soil's moisture, attenuation, noise and clutter belong here too: the detector only
# knows the soil type the supervisor chose. Not allowed inside a longer name either (true_depth_m, object_kind).
TRUTH_NAMES = {
    "kind", "is_target", "depth_m", "metal_mass", "size_m",
    "objects", "md_field", "gpr_field",
    "moisture", "gpr_attenuation", "md_noise", "md_background", "gpr_noise", "gpr_clutter", "rock_weight",
    "truth", "truths", "ground_truth", "target", "targets", "outcomes", "fp_by_cause", "evaluation_label",
}  # fmt: skip
# Not allowed as any word of a name either.
TRUTH_WORDS = {"true", "mine", "mines", "buried", "object"}
# The detector's estimates (est_depth_m) may carry the name of what they estimate.
ESTIMATE = "est_"
# Fields of the ground truth whose names the API also uses for something else.
ALSO_PUBLIC = {
    "id": "every row has one",
    "x": "positions: the API gives lat and lon; an object's own under another name (object_x, true_x) is caught",
    "y": "as x",
    "key": "the soil type's name, chosen by the supervisor",
    "label": "as key",
    "soil": "as key",
    "permittivity": "the profile's nominal value for the chosen soil type, which the detector assumes "
    "(docs/EVALUATION_PROTOCOL.md, Known limitations)",
    "seed": "scenario_seed goes to the supervisor only (test_only_the_supervisor_gets_the_scenario_seed)",
}


def relabelled(sim: Simulation) -> Simulation:
    objects = tuple(dataclasses.replace(o, kind=RELABEL[o.kind]) for o in sim.scenario.objects)
    scenario = dataclasses.replace(sim.scenario, objects=objects)
    return Simulation(sim.config, sim.plan, scenario, SensorModel(scenario, noise_seed=sim.config.seed))


def readings(sim: Simulation) -> list[Reading]:
    return [Reading(fs.t_s, fs.x, fs.y, fs.alt_m, ss.md, ss.gpr_amp, ss.gpr_twt_ns) for fs, ss in sim.samples()]


def assert_only_labels_differ(sim: Simulation, other: Simulation) -> None:
    pairs = list(zip(sim.scenario.objects, other.scenario.objects, strict=True))
    assert all(a.kind != b.kind for a, b in pairs)
    assert any(a.is_target != b.is_target for a, b in pairs)
    assert all(dataclasses.replace(a, kind=b.kind) == b for a, b in pairs)
    assert dataclasses.replace(sim.scenario, objects=other.scenario.objects) == other.scenario


# The detection path


def imported_modules(path: Path, package: str) -> set[str]:
    """Every module a file imports, and for `from m import n` also m.n (n may be a module)."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = package.rsplit(".", node.level - 1)[0] if node.level else ""
            module = ".".join(part for part in (base, node.module) if part)
            names |= {module} | {f"{module}.{a.name}" for a in node.names}
    return names


DETECTION_DIR = Path(app.detection.__file__).parent
# detection/evaluation.py scores detections against the truth after they are made; the mission runner never uses it.
OFFLINE_SCORER = "app.detection.evaluation"


@pytest.mark.parametrize("module", sorted(p.name for p in DETECTION_DIR.glob("*.py") if p.stem != "evaluation"))
def test_the_detectors_import_only_their_own_modules_and_the_standard_library(module):
    imported = imported_modules(DETECTION_DIR / module, "app.detection")
    own = {m for m in imported if m.split(".")[:2] == ["app", "detection"]}
    outside = {m for m in imported - own if m.split(".")[0] not in sys.stdlib_module_names}
    assert not outside
    assert not {m for m in imported if m.startswith(OFFLINE_SCORER)}


def test_the_mission_runner_never_uses_the_offline_scorer():
    api = DETECTION_DIR.parent / "api"
    for path in [*api.glob("*.py"), *(DETECTION_DIR.parent / "uav").glob("*.py")]:
        package = f"app.{path.parent.name}"
        imported = imported_modules(path, package)
        assert not {m for m in imported if m.startswith((OFFLINE_SCORER, "app.evaluation.harness"))}, path.name


@pytest.mark.parametrize(
    ("soil_type", "seed"), [("dry_sand", EVALUATION_SEEDS[0]), ("wet_clay", 77), ("mineralized_rocky", 11)]
)
def test_objects_with_other_labels_give_the_same_readings_and_detections(soil_type, seed):
    """The direct leak test of the isolation contract: the labels change, the numbers do not, so neither may
    anything the sensors or the detectors produce."""
    config = SimulationConfig(soil_type=soil_type, seed=seed, **STANDARD_SURVEY)
    sim, other = build_simulation(config), relabelled(build_simulation(config))
    assert_only_labels_differ(sim, other)

    ours, theirs = readings(sim), readings(other)
    assert ours == theirs
    context = SurveyContext(soil_type, config.altitude_m, config.speed_mps, config.line_spacing_m, config.dt_s)
    adaptive = detect_adaptive(ours, context)
    assert adaptive and adaptive == detect_adaptive(theirs, context)
    assert detect_baseline(ours) == detect_baseline(theirs)


def test_px4_frames_over_objects_with_other_labels_are_the_same():
    """With PX4 the sensor model reads the objects at PX4's position: over each object, and between them."""
    config = SimulationConfig(soil_type="dry_sand", seed=EVALUATION_SEEDS[0], **STANDARD_SURVEY)
    sim, other = build_simulation(config), relabelled(build_simulation(config))
    assert_only_labels_differ(sim, other)
    points = [(o.x, o.y) for o in sim.scenario.objects] + list(sim.plan.waypoints_xy[1:-1])

    def frames(s: Simulation) -> list:
        progress = PathProgress(s.plan)
        out = []
        for x, y in points:
            lat, lon = s.frame.to_latlon(x, y)
            state = Px4State(
                lat_deg=lat, lon_deg=lon, absolute_alt_m=431.5, relative_alt_m=1.5, v_north_m_s=0.0, v_east_m_s=2.0,
                v_down_m_s=0.0, heading_deg=90.0, battery_pct=87.4, current=1, total=len(s.plan.waypoints_xy),
            )
            out.append(build_frame(state, 12.0, s, progress))
        return out

    ours = frames(sim)
    assert all(f.sensor is not None for f in ours)
    assert ours == frames(other)


# Through the backend


def strip(value, names: set[str]):
    """value without the keys in names, at any depth: what differs between two runs of the same mission."""
    if isinstance(value, dict):
        return {k: strip(v, names) for k, v in value.items() if k not in names}
    if isinstance(value, list):
        return [strip(v, names) for v in value]
    return value


RUN_SPECIFIC = {"id", "mission_id", "created_at", "started_at", "completed_at"}


def run_mission(client, headers) -> int:
    mission_id = client.post("/api/missions", json=mission_body(), headers=headers).json()["id"]
    r = client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=headers)
    assert r.status_code == 202, r.text
    assert wait_until_finished(client, mission_id, headers)["status"] == "completed"
    return mission_id


def everything_sent_about(client, headers, mission_id: int) -> dict:
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        snapshot = ws.receive_json()
    with Session(client.app.state.engine) as session:
        # In the order they were written: PostgreSQL returns updated rows (the live detections) in another order.
        stored = {
            name: [
                row.model_dump()
                for row in session.exec(select(table).where(table.mission_id == mission_id).order_by(table.id))
            ]
            for name, table in (("readings", SensorReading), ("detection_rows", Detection))
        }
    sent = {
        **stored,
        "mission": client.get(f"/api/missions/{mission_id}", headers=headers).json(),
        "telemetry": client.get(f"/api/missions/{mission_id}/telemetry", headers=headers).json(),
        "detections": client.get(f"/api/missions/{mission_id}/detections", headers=headers).json(),
        "profile": client.get(f"/api/missions/{mission_id}/profile", headers=headers).json(),
        "heatmap": client.get(f"/api/missions/{mission_id}/heatmap", headers=headers).json(),
        "snapshot": snapshot,
    }
    return strip(sent, RUN_SPECIFIC)


def test_a_mission_over_objects_with_other_labels_stores_and_sends_the_same(client, monkeypatch):
    """The whole path: simulator, mission runner (live adaptive detections, then the baseline), database, REST and
    the WebSocket snapshot and the heatmap."""
    sup = auth_headers(client, "supervisor")
    first = everything_sent_about(client, sup, run_mission(client, sup))

    built: list[Simulation] = []

    def build_relabelled(config: SimulationConfig) -> Simulation:
        built.append(relabelled(build_simulation(config)))
        return built[-1]

    monkeypatch.setattr(simulated_source, "build_simulation", build_relabelled)
    second = everything_sent_about(client, sup, run_mission(client, sup))

    assert first["readings"] and first["detections"]
    assert first == second
    assert len(built) == 1  # the second mission flew over the relabelled objects
    assert_only_labels_differ(build_simulation(built[0].config), built[0])


def test_the_comparison_sees_every_column_of_the_readings_and_detections(client):
    sup = auth_headers(client, "supervisor")
    sent = everything_sent_about(client, sup, run_mission(client, sup))
    for name, table in (("readings", SensorReading), ("detection_rows", Detection)):
        assert set(sent[name][0]) == {c.name for c in table.__table__.columns} - RUN_SPECIFIC


# What the API sends


def names_in(value) -> set[str]:
    """Every key at any depth, in dicts inside lists too."""
    if isinstance(value, dict):
        return set(value) | {n for v in value.values() for n in names_in(v)}
    if isinstance(value, list):
        return {n for v in value for n in names_in(v)}
    return set()


def truth_names(names: set[str]) -> set[str]:
    def named_after_the_truth(name: str) -> bool:
        name = name.lower()
        if name in TRUTH_NAMES or TRUTH_WORDS & set(name.split("_")):
            return True
        return not name.startswith(ESTIMATE) and any(f"_{t}_" in f"_{name}_" for t in TRUTH_NAMES)

    return {n for n in names if named_after_the_truth(n)}


def test_the_list_of_names_covers_every_field_of_the_ground_truth():
    fields = {f.name for t in (BuriedObject, Scenario, SoilProfile, TruthObject) for f in dataclasses.fields(t)}
    assert fields - set(ALSO_PUBLIC) <= TRUTH_NAMES
    assert not truth_names(set(ALSO_PUBLIC))


def test_no_rest_response_or_live_event_names_the_ground_truth(client):
    sup, field = auth_headers(client, "supervisor"), auth_headers(client, "field")
    password = next(u["password"] for u in DEMO_USERS if u["username"] == "field")
    body = mission_body()
    sent = [
        client.post("/api/auth/login", json={"username": "field", "password": password}).json(),
        client.get("/api/auth/me", headers=sup).json(),
        client.post("/api/missions/check", json=body, headers=sup).json(),
    ]
    created = client.post("/api/missions", json=body, headers=sup).json()
    mission_id = created["id"]
    token = sup["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        sent.append(ws.receive_json())
        sent.append(client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup).json())
        while True:
            event = ws.receive_json()
            sent.append(event)
            if event["type"] == "mission" and event["status"] in ("completed", "stopped", "failed"):
                break
    events = {e["type"] for e in sent if isinstance(e, dict) and "type" in e}
    assert {"snapshot", "telemetry", "detection_created", "mission"} <= events

    detections = client.get(f"/api/missions/{mission_id}/detections", headers=field).json()
    assert detections
    sent += [
        created,
        client.get("/api/missions", headers=field).json(),
        client.get(f"/api/missions/{mission_id}", headers=field).json(),
        client.get("/api/missions/history", headers=field).json(),
        client.get(f"/api/missions/{mission_id}/telemetry", headers=field).json(),
        client.get(f"/api/missions/{mission_id}/profile", headers=field).json(),
        client.get(f"/api/missions/{mission_id}/heatmap", headers=field).json(),
        detections,
        client.get(f"/api/detections/{detections[0]['id']}", headers=field).json(),
        client.patch(f"/api/detections/{detections[0]['id']}", json={"status": "false_alarm"}, headers=field).json(),
    ]
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        sent.append(ws.receive_json())  # the snapshot of a finished mission, with all its detections

    names = names_in(sent)
    assert {"md_evidence", "est_depth_m", "scenario_seed", "battery_pct"} <= names  # the walk reached the details
    assert not truth_names(names)


def test_no_schema_in_the_openapi_document_names_the_ground_truth(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    properties = {n for schema in schemas.values() for n in schema.get("properties", {})}
    assert {"scenario_seed", "est_depth_m"} <= properties
    assert not truth_names(properties | set(schemas))


def test_no_table_stores_the_ground_truth():
    columns = {c.name for table in SQLModel.metadata.tables.values() for c in table.columns}
    assert {"md", "gpr_amp", "est_depth_m"} <= columns
    assert not truth_names(columns | set(SQLModel.metadata.tables))


def test_the_evaluation_report_scores_against_the_truth_but_gives_no_positions(client):
    """/api/evaluation is the offline evaluation: the truth joined to the detections after they were made, on the
    evaluation seeds. It names the kinds of object, by design, but only as counts per soil type."""
    report = client.get("/api/evaluation", headers=auth_headers(client, "field")).json()
    names = names_in(report)
    assert {"targets", "outcomes", "low_metal_mine"} <= names
    assert not names & {"x", "y", "lat", "lon", "depth_m", "objects", "scenario_seed"}


def test_only_the_supervisor_gets_the_scenario_seed(client):
    """With the seed and this code the buried objects of a simulated mission can be rebuilt."""
    sup, field = auth_headers(client, "supervisor"), auth_headers(client, "field")
    mission_id = run_mission(client, sup)

    def seeds(headers) -> list:
        token = headers["Authorization"].removeprefix("Bearer ")
        with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
            snapshot = ws.receive_json()
        return [
            client.get(f"/api/missions/{mission_id}", headers=headers).json()["scenario_seed"],
            client.get("/api/missions", headers=headers).json()[0]["scenario_seed"],
            client.get("/api/missions/history", headers=headers).json()["missions"][0]["mission"]["scenario_seed"],
            snapshot["mission"]["scenario_seed"],
        ]

    assert seeds(sup) == [mission_body()["scenario_seed"]] * 4
    assert seeds(field) == [None] * 4

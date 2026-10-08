"""The sensor heatmap's grid (app/api/heatmap.py) and the PDF report (app/report/)."""

from __future__ import annotations

import io
import math

import pytest
from conftest import auth_headers, mission_body, wait_until_finished
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlmodel import Session

from app.api.heatmap import GPR_FULL_SCALE, MAX_CELLS, MAX_ROWS, MD_FULL_SCALE, sensor_grid
from app.config import Settings
from app.main import create_app
from app.models import Detection
from app.report.fonts import find_font
from app.report.pdf import NOTICE_AR, NOTICE_EN
from app.simulation import DEMO_AREA, plan_survey

# The demo field, 60 x 40 m, lanes every 2 m.
PLAN = plan_survey(DEMO_AREA, 2.0)


def reading(x: float, y: float, md: float, gpr: float) -> tuple[float, float, float, float]:
    return (*PLAN.frame.to_latlon(x, y), md, gpr)


# The grid


def test_each_lane_is_a_row_and_a_cell_keeps_its_strongest_reading():
    lane_y = [y for _, y in PLAN.waypoints_xy[::2]]
    grid = sensor_grid(DEMO_AREA, 2.0, [reading(0.0, lane_y[3], 0.2, 0.01), reading(0.1, lane_y[3], 0.6, 0.02)])
    assert grid.rows == len(lane_y)
    assert grid.cols == math.ceil(PLAN.width_m / 0.5)
    assert grid.readings == 2
    filled = [i for i, v in enumerate(grid.md) if v is not None]
    assert len(filled) == 1  # both readings in one cell, on the fourth lane from the south
    assert filled[0] // grid.cols == grid.rows - 1 - 3
    assert grid.md[filled[0]] == pytest.approx(0.6 / MD_FULL_SCALE)
    assert grid.gpr[filled[0]] == pytest.approx(0.02 / GPR_FULL_SCALE)


def test_values_are_scaled_to_the_full_scale_and_capped_at_one():
    y = PLAN.waypoints_xy[0][1]
    grid = sensor_grid(DEMO_AREA, 2.0, [reading(-20, y, 3.0, 5.0), reading(20, y, -0.1, 0.0)])
    values = sorted(v for v in grid.md if v is not None)
    assert values == [0.0, 1.0]
    assert max(v for v in grid.gpr if v is not None) == 1.0


def test_the_grid_covers_the_area_and_readings_far_outside_are_left_out():
    grid = sensor_grid(DEMO_AREA, 2.0, [reading(0, 0, 0.1, 0.1), reading(500, 0, 0.1, 0.1)])
    assert grid.readings == 1
    (south, west), (north, east) = grid.bounds
    for lat, lon in DEMO_AREA:
        assert south - 1e-9 <= lat <= north + 1e-9 and west - 1e-9 <= lon <= east + 1e-9


def test_a_big_survey_gets_fewer_bigger_cells():
    # 300 x 300 m with lanes every 0.5 m: 600 lanes, 600 cells along each.
    side = 300 / 111_320
    area = [(24.0, 47.0), (24.0 + side, 47.0), (24.0 + side, 47.0 + side * 1.1), (24.0, 47.0 + side * 1.1)]
    grid = sensor_grid(area, 0.5, [])
    assert grid.rows <= MAX_ROWS and grid.rows * grid.cols <= MAX_CELLS
    assert grid.cell_m[0] > 0.5 and grid.cell_m[1] >= 1.0
    assert all(v is None for v in grid.md)


# Through the API


@pytest.fixture
def flown(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
    return wait_until_finished(client, mission_id, sup)


def test_the_heatmap_holds_every_reading_of_the_mission(client, flown):
    field = auth_headers(client, "field")
    heatmap = client.get(f"/api/missions/{flown['id']}/heatmap", headers=field).json()
    assert heatmap["readings"] == flown["stats"]["sensor_readings"] > 0
    assert len(heatmap["md"]) == len(heatmap["gpr"]) == heatmap["rows"] * heatmap["cols"]
    assert heatmap["full_scale"] == {"md": MD_FULL_SCALE, "gpr": GPR_FULL_SCALE}
    values = [v for v in heatmap["md"] if v is not None]
    assert values and all(0 <= v <= 1 for v in values)
    assert client.get("/api/missions/999/heatmap", headers=field).status_code == 404
    assert client.get(f"/api/missions/{flown['id']}/heatmap").status_code == 401


def test_a_planned_mission_has_an_empty_heatmap(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    heatmap = client.get(f"/api/missions/{mission_id}/heatmap", headers=sup).json()
    assert heatmap["readings"] == 0 and set(heatmap["md"]) == {None}


# The report


def pages_text(pdf: bytes) -> list[str]:
    return [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]


def assert_every_page_has_the_notice(pages: list[str]) -> None:
    for number, text in enumerate(pages, start=1):
        assert NOTICE_EN in text
        assert NOTICE_AR in text
        assert f"Page {number} of {len(pages)}" in text


def test_the_supervisor_gets_a_pdf_report(client, flown):
    sup = auth_headers(client, "supervisor")
    r = client.get(f"/api/missions/{flown['id']}/report.pdf", headers=sup)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'attachment; filename="mission-{flown["id"]}-report.pdf"'
    assert r.content.startswith(b"%PDF-") and r.content.rstrip().endswith(b"%%EOF")

    pages = pages_text(r.content)
    assert_every_page_has_the_notice(pages)
    text = "\n".join(pages)
    for words in ("Survey report", "تقرير المسح", "Test survey", "Built-in simulator", "Completed", "Complete (100%)"):
        assert words in text
    detections = client.get(f"/api/missions/{flown['id']}/detections?method=adaptive", headers=sup).json()
    assert detections
    for d in detections:
        assert f"{d['lat']:.6f}" in text and f"{d['confidence']:.2f}" in text
    reported = sum(d["category"] != "clutter" for d in detections)
    assert f"Verification counts the {reported} reported" in text


def test_the_field_operator_cannot_get_the_report(client, flown):
    assert client.get(f"/api/missions/{flown['id']}/report.pdf", headers=auth_headers(client, "field")).status_code == 403
    assert client.get(f"/api/missions/{flown['id']}/report.pdf").status_code == 401
    assert client.get("/api/missions/999/report.pdf", headers=auth_headers(client, "supervisor")).status_code == 404


def test_an_arabic_name_and_many_detections_over_several_pages(client):
    sup = auth_headers(client, "supervisor")
    name = "مسح الحقل الشمالي"
    mission_id = client.post("/api/missions", json=mission_body(name=name), headers=sup).json()["id"]
    with Session(client.app.state.engine) as session:
        for i in range(80):
            session.add(
                Detection(
                    mission_id=mission_id, method="adaptive", lat=24.1394 + i * 1e-6, lon=47.262, category="suspect",
                    confidence=0.5, peak_md=0.1, peak_gpr=0.1, n_hits=3, explanation="test",
                )
            )  # fmt: skip
        session.commit()
    r = client.get(f"/api/missions/{mission_id}/report.pdf", headers=sup)
    assert r.status_code == 200, r.text
    pages = pages_text(r.content)
    assert len(pages) >= 3
    assert_every_page_has_the_notice(pages)
    assert name in pages[0]
    assert "Planned, not flown yet" in pages[0] and "Not started" in pages[0]
    # The table's headings again on each page it runs over.
    assert sum("Latitude" in p for p in pages) >= 2


def test_without_a_font_with_arabic_letters_the_report_says_what_to_set(database_url, tmp_path):
    settings = Settings(database_url=database_url, secret_key="test-secret", report_font=str(tmp_path / "none.ttf"))
    with TestClient(create_app(settings)) as client:
        sup = auth_headers(client, "supervisor")
        mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
        r = client.get(f"/api/missions/{mission_id}/report.pdf", headers=sup)
    assert r.status_code == 503
    assert "REPORT_FONT" in r.json()["detail"]


def test_a_font_with_arabic_letters_is_found_on_this_machine():
    font = find_font()
    assert font.regular.is_file() and font.bold.is_file()

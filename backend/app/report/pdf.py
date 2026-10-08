"""The mission report as a PDF: what was flown, how it ended, a map and the potential detections.

Made with fpdf2 on the server, from the stored data only. Arabic text (mission names, the headings and the notice)
is shaped with HarfBuzz and laid out right to left by fpdf2's bidirectional text support. Every page carries the
notice that the data is simulated and the detections are potential ones for trained personnel to verify.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from fpdf import FPDF, FontFace

from app.models import Detection, Mission
from app.simulation import plan_survey
from app.simulation.geo import bounding_box

from .fonts import ReportFont

NOTICE_EN = "Simulated data — potential detections for verification by trained personnel"
NOTICE_AR = "بيانات محاكاة — كشوفات محتملة يتحقق منها أفراد مدرّبون"

CATEGORY_ORDER = ("high", "suspect", "clutter")
CATEGORY_LABELS = {"high": "High priority", "suspect": "Needs verification", "clutter": "Likely clutter"}
VERIFICATION_LABELS = {
    "pending": "Awaiting verification",
    "confirmed_by_team": "Confirmed by team",
    "false_alarm": "False alarm",
}
STATUS_LABELS = {
    "planned": "Planned, not flown yet",
    "running": "Surveying (this report was made during the flight)",
    "completed": "Completed",
    "stopped": "Stopped early by the supervisor",
    "failed": "Failed",
}
SOURCE_LABELS = {"simulated": "Built-in simulator", "px4": "PX4 SITL"}
SENSOR_LABELS = {"complete": "Complete", "partial": "Partial", "failed": "Failed", "not_started": "Not started"}
SOIL_LABELS = {"dry_sand": "Dry sand", "wet_clay": "Wet clay", "mineralized_rocky": "Mineralised rocky soil"}

# The map colours of the web page (web/src/theme.ts), on white paper.
INK = "#1d2a24"
MUTED = "#5b6660"
RULE = "#c9cfcb"
HAZARD = "#c62d1f"
AMBER = "#e0a526"
SURVEY = "#1f5fad"
CLUTTER = "#8a948c"
CATEGORY_COLORS = {"high": HAZARD, "suspect": AMBER, "clutter": CLUTTER}

FONT = "report"
MAP_MAX_H = 115.0  # mm
MAP_EDGE_MM = 8.0  # around the survey, for the north arrow and the scale bar


def _when(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def right_to_left(text: str) -> bool:
    """Whether the first letter is Hebrew or Arabic, so the line reads from the right (as the Unicode bidi rules say)."""
    for ch in text:
        if ch.isalpha():
            return "\u0590" <= ch <= "\u08ff" or "\ufb1d" <= ch <= "\ufeff"
    return False


def sensor_text(mission: Mission) -> str:
    """As the page's badge: "Partial (62%)", or "Not recorded" for missions flown before it was."""
    if mission.status == "running":
        return "Collecting"
    if mission.sensor_collection is None:
        return "Not recorded"
    label = SENSOR_LABELS.get(mission.sensor_collection, mission.sensor_collection)
    if mission.sensor_collection in ("complete", "partial") and mission.sensor_coverage is not None:
        return f"{label} ({math.floor(mission.sensor_coverage * 100)}%)"
    return label


def ordered(detections: Sequence[Detection]) -> list[Detection]:
    """The adaptive detections, high priority first, then by score."""
    rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    return sorted(
        (d for d in detections if d.method == "adaptive"), key=lambda d: (rank.get(d.category, 9), -d.confidence, d.id)
    )


@dataclass(frozen=True)
class Summary:
    categories: dict[str, int]
    verification: dict[str, int]  # of the reported ones (high priority and needs verification), as in History

    @property
    def reported(self) -> int:
        return sum(self.verification.values())


def summarize(detections: Sequence[Detection]) -> Summary:
    categories = dict.fromkeys(CATEGORY_ORDER, 0)
    verification = dict.fromkeys(VERIFICATION_LABELS, 0)
    for d in detections:
        if d.method != "adaptive":
            continue
        categories[d.category] = categories.get(d.category, 0) + 1
        if d.category != "clutter":
            verification[d.status] = verification.get(d.status, 0) + 1
    return Summary(categories, verification)


class _Report(FPDF):
    def footer(self) -> None:
        self.set_y(-17)
        self.set_draw_color(RULE)
        self.set_line_width(0.2)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(-15.5)
        self.set_font(FONT, "", 8)
        self.set_text_color(MUTED)
        self.cell(0, 4.5, NOTICE_EN, new_x="LMARGIN")
        self.cell(0, 4.5, f"Page {self.page_no()} of {{nb}}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 4.5, NOTICE_AR, align="R")


def _heading(pdf: FPDF, english: str, arabic: str, keep_mm: float = 25) -> None:
    """keep_mm: room the section needs under its heading, else it starts on a new page."""
    if pdf.get_y() + 14 + keep_mm > pdf.page_break_trigger:
        pdf.add_page()
    pdf.ln(3)
    pdf.set_font(FONT, "B", 12)
    pdf.set_text_color(INK)
    pdf.cell(0, 7, english, new_x="LMARGIN")
    pdf.cell(0, 7, arabic, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(RULE)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)


def _facts(pdf: FPDF, rows: Sequence[tuple[str, str]]) -> None:
    for label, value in rows:
        pdf.set_font(FONT, "B", 9.5)
        pdf.set_text_color(MUTED)
        pdf.cell(34, 5.5, label)
        pdf.set_font(FONT, "", 9.5)
        pdf.set_text_color(INK)
        pdf.multi_cell(0, 5.5, value, align="L", new_x="LMARGIN", new_y="NEXT")


def _nice_length(target_m: float) -> float:
    """1, 2 or 5 times a power of ten, at most target_m."""
    power = 10 ** math.floor(math.log10(target_m))
    return max(m * power for m in (1, 2, 5) if m * power <= target_m)


def _map(pdf: FPDF, mission: Mission, detections: Sequence[Detection], track: Sequence[tuple[float, float]]) -> None:
    """Area, planned lanes, flown track and detections to scale, north up, in the survey's own frame."""
    plan = plan_survey(mission.area, mission.line_spacing_m)
    to_xy = plan.frame.to_xy
    area = [to_xy(lat, lon) for lat, lon in mission.area]
    path = [to_xy(lat, lon) for lat, lon in mission.path]
    flown = [to_xy(lat, lon) for lat, lon in track]
    marks = [(d, to_xy(d.lat, d.lon)) for d in detections]
    xmin, ymin, xmax, ymax = bounding_box(area + path + flown + [p for _, p in marks])

    full_w = pdf.w - pdf.l_margin - pdf.r_margin
    edge = MAP_EDGE_MM
    scale = min((full_w - 2 * edge) / (xmax - xmin), (MAP_MAX_H - 2 * edge) / (ymax - ymin))  # mm per metre
    w, h = (xmax - xmin) * scale + 2 * edge, (ymax - ymin) * scale + 2 * edge
    _heading(pdf, "Map", "الخريطة", keep_mm=h + 10)
    left, top = pdf.l_margin + (full_w - w) / 2, pdf.get_y()

    def at(p: tuple[float, float]) -> tuple[float, float]:
        return left + edge + (p[0] - xmin) * scale, top + edge + (ymax - p[1]) * scale

    pdf.set_fill_color("#f4f5f3")
    pdf.set_draw_color(RULE)
    pdf.set_line_width(0.2)
    pdf.rect(left, top, w, h, style="DF")

    pdf.set_fill_color("#fbe9e7")
    pdf.set_draw_color(HAZARD)
    pdf.set_line_width(0.5)
    pdf.set_dash_pattern(dash=2, gap=1.5)
    pdf.polygon([at(p) for p in area], style="DF")
    pdf.set_dash_pattern()

    if len(path) > 1:
        pdf.set_draw_color("#8f9893")
        pdf.set_line_width(0.15)
        pdf.set_dash_pattern(dash=0.8, gap=0.8)
        pdf.polyline([at(p) for p in path])
        pdf.set_dash_pattern()

    # Every point closer than a third of a millimetre to the last one drawn adds nothing to the line.
    points: list[tuple[float, float]] = []
    for p in flown:
        q = at(p)
        if not points or math.dist(points[-1], q) >= 0.33:
            points.append(q)
    if len(points) > 1:
        pdf.set_draw_color(SURVEY)
        pdf.set_line_width(0.35)
        pdf.polyline(points)

    pdf.set_font(FONT, "B", 6.5)
    pdf.set_line_width(0.3)
    pdf.set_draw_color("#ffffff")
    for category in reversed(CATEGORY_ORDER):  # high priority on top
        for d, p in marks:
            if d.category != category:
                continue
            x, y = at(p)
            r = 1.3 if category == "clutter" else 1.7
            pdf.set_fill_color(CATEGORY_COLORS[category])
            pdf.ellipse(x - r, y - r, 2 * r, 2 * r, style="DF")
            if category != "clutter":
                pdf.set_text_color(INK)
                pdf.text(x + r + 0.6, y + 1, f"#{d.id}")

    # North arrow in the top right corner, a scale bar in the bottom left one, both outside the survey.
    nx, ny = left + w - 3.5, top + 1.6
    pdf.set_fill_color(INK)
    pdf.polygon([(nx, ny), (nx + 1.6, ny + 4), (nx - 1.6, ny + 4)], style="F")
    pdf.set_font(FONT, "B", 7)
    pdf.set_text_color(INK)
    pdf.text(nx - 5, ny + 3.6, "N")
    length = _nice_length((xmax - xmin) / 4)
    sx, sy = left + 3, top + h - 3
    pdf.set_draw_color(INK)
    pdf.set_line_width(0.5)
    pdf.line(sx, sy, sx + length * scale, sy)
    pdf.set_font(FONT, "", 7)
    pdf.text(sx + length * scale + 1.5, sy + 0.9, f"{length:g} m")

    pdf.set_y(top + h + 2)
    _legend(pdf)


def _legend(pdf: FPDF) -> None:
    pdf.set_font(FONT, "", 8)
    pdf.set_text_color(MUTED)
    x, y = pdf.l_margin, pdf.get_y() + 2.2
    items = [("dot", CATEGORY_COLORS[c], CATEGORY_LABELS[c]) for c in CATEGORY_ORDER] + [
        ("line", SURVEY, "Flown track"),
        ("dash", "#8f9893", "Planned lanes"),
        ("dash", HAZARD, "Survey area"),
    ]
    for kind, colour, label in items:
        if kind == "dot":
            pdf.set_fill_color(colour)
            pdf.ellipse(x, y - 1.2, 2.4, 2.4, style="F")
        else:
            pdf.set_draw_color(colour)
            pdf.set_line_width(0.5 if kind == "line" else 0.35)
            if kind == "dash":
                pdf.set_dash_pattern(dash=1, gap=0.8)
            pdf.line(x, y, x + 5, y)
            pdf.set_dash_pattern()
        mark_w = 3.4 if kind == "dot" else 6.4
        pdf.text(x + mark_w, y + 1.1, label)
        x += mark_w + pdf.get_string_width(label) + 5
    pdf.set_y(y + 4)


def _summary(pdf: FPDF, summary: Summary) -> None:
    cells = [(str(summary.categories[c]), CATEGORY_LABELS[c]) for c in CATEGORY_ORDER] + [
        (str(summary.verification[s]), VERIFICATION_LABELS[s]) for s in ("confirmed_by_team", "false_alarm", "pending")
    ]
    width = (pdf.w - pdf.l_margin - pdf.r_margin) / len(cells)
    top = pdf.get_y()
    for i, (number, label) in enumerate(cells):
        x = pdf.l_margin + i * width
        pdf.set_xy(x, top)
        pdf.set_font(FONT, "B", 15)
        pdf.set_text_color(INK)
        pdf.cell(width, 8, number, align="C")
        pdf.set_xy(x, top + 8)
        pdf.set_font(FONT, "", 8)
        pdf.set_text_color(MUTED)
        pdf.multi_cell(width, 3.8, label, align="C")
    pdf.set_y(top + 17)
    pdf.set_font(FONT, "", 8.5)
    pdf.set_text_color(MUTED)
    pdf.multi_cell(
        0,
        4.2,
        f"Potential detections from the adaptive classifier. Verification counts the {summary.reported} reported "
        f"{'one' if summary.reported == 1 else 'ones'} (high priority and needs verification), as recorded by field "
        "personnel.",
        align="L",
        new_x="LMARGIN",
        new_y="NEXT",
    )


def _table(pdf: FPDF, detections: Sequence[Detection]) -> None:
    pdf.set_font(FONT, "", 8.5)
    pdf.set_text_color(INK)
    if not detections:
        pdf.cell(0, 6, "No potential detections.", new_x="LMARGIN", new_y="NEXT")
        return
    heading = FontFace(emphasis="B", color=INK, fill_color="#e8ebe8")
    pdf.set_fill_color("#ffffff")  # every other row; the rest take cell_fill_color
    with pdf.table(
        col_widths=(10, 34, 14, 26, 26, 70),
        text_align=("RIGHT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "LEFT"),
        headings_style=heading,
        line_height=5,
        borders_layout="HORIZONTAL_LINES",
        cell_fill_color="#f5f6f4",
        cell_fill_mode="ROWS",
        repeat_headings=1,
    ) as table:
        table.row(["#", "Category", "Score", "Latitude", "Longitude", "Verification"])
        for d in detections:
            verified = VERIFICATION_LABELS.get(d.status, d.status)
            if d.verified_at is not None:
                verified += f", {_when(d.verified_at)}"
            table.row(
                [
                    str(d.id),
                    CATEGORY_LABELS.get(d.category, d.category),
                    f"{d.confidence:.2f}",
                    f"{d.lat:.6f}",
                    f"{d.lon:.6f}",
                    verified,
                ]
            )
    pdf.ln(2)
    pdf.set_font(FONT, "", 8)
    pdf.set_text_color(MUTED)
    pdf.multi_cell(
        0,
        4,
        "Coordinates in WGS 84 degrees, where the classifier placed each detection. The score ranks detections for "
        "verification (0 to 1); it is not a probability. The fixed-threshold baseline's alarms are not listed.",
        align="L",
        new_x="LMARGIN",
        new_y="NEXT",
    )


def mission_report(
    mission: Mission,
    detections: Sequence[Detection],
    track: Sequence[tuple[float, float]],
    font: ReportFont,
    now: datetime | None = None,
) -> bytes:
    """detections: the mission's (both methods; the report lists the adaptive ones). track: the flown (lat, lon)."""
    pdf = _Report(format="A4")
    pdf.set_title(f"Survey report - {mission.name}")
    pdf.set_creator("UAV landmine detection prototype")
    pdf.add_font(FONT, "", str(font.regular))
    pdf.add_font(FONT, "B", str(font.bold))
    pdf.set_text_shaping(True)
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, margin=22)
    pdf.add_page()

    pdf.set_font(FONT, "B", 18)
    pdf.set_text_color(INK)
    pdf.cell(0, 9, "Survey report", new_x="LMARGIN")
    pdf.cell(0, 9, "تقرير المسح", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "B", 12.5)
    pdf.multi_cell(0, 6.5, mission.name, align="R" if right_to_left(mission.name) else "L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 8.5)
    pdf.set_text_color(MUTED)
    made = _when(now or datetime.now(UTC))
    pdf.cell(0, 5, f"Mission #{mission.id}. Made {made} from the stored mission data.", new_x="LMARGIN", new_y="NEXT")

    _heading(pdf, "Mission", "المهمة")
    flight = STATUS_LABELS.get(mission.status, mission.status)
    if mission.error:
        flight += f": {mission.error}"
    sensors = f"{sensor_text(mission)}, {mission.sensor_reading_count:,} readings"
    if mission.sensor_note and mission.status != "running":
        sensors += f". {mission.sensor_note}"
    plan = plan_survey(mission.area, mission.line_spacing_m)
    _facts(
        pdf,
        [
            ("Date", f"Planned {_when(mission.created_at)}, flown {_when(mission.started_at)}, "
                     f"ended {_when(mission.completed_at)}"),
            ("Flown by", SOURCE_LABELS.get(mission.uav_source, mission.uav_source)),
            ("Flight", flight),
            ("Sensors", sensors),
            ("Survey", f"{SOIL_LABELS.get(mission.soil_type, mission.soil_type)}; area {plan.width_m:.0f} × "
                       f"{plan.height_m:.0f} m; lanes every {mission.line_spacing_m:g} m; sensors "
                       f"{mission.altitude_m:g} m above the ground at {mission.speed_mps:g} m/s; "
                       f"path {mission.path_length_m:,.0f} m"),
        ],
    )  # fmt: skip

    listed = ordered(detections)
    _heading(pdf, "Summary", "الملخص")
    _summary(pdf, summarize(detections))
    _map(pdf, mission, listed, track)
    _heading(pdf, "Detections", "الكشوفات")
    _table(pdf, listed)
    return bytes(pdf.output())

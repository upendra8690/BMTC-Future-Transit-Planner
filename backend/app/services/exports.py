"""CSV and PDF exports. Every export carries its classification and notice."""

from __future__ import annotations

import csv
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import CLASS_SCENARIO
from .scenarios import SCENARIO_NOTICE


def escape(text: str) -> str:
    """Escape &, < and > for ReportLab paragraph markup. These are the same three replacements that
    xml.sax.saxutils.escape makes; this module only writes text out and never parses XML."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cell(value: Any) -> str:
    """Neutralise spreadsheet formula injection: values starting with = + - @ are prefixed with an apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def scenarios_csv(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "classification", "name", "year", "route_code", "origin", "destination",
            "first_departure", "last_departure", "frequency_minutes", "operating_days",
            "intermediate_stops", "estimated_distance_km", "estimated_journey_minutes",
            "departures_per_day", "departures_per_week", "notice",
        ]
    )
    for payload, estimate in rows:
        writer.writerow(
            [_cell(v) for v in [
                CLASS_SCENARIO,
                payload["name"],
                payload["year"],
                payload["route_code"],
                payload["origin"]["name"],
                payload["destination"]["name"],
                payload["first_departure"],
                payload["last_departure"],
                payload["frequency_minutes"],
                " ".join(payload["operating_days"]),
                "; ".join(stop["name"] for stop in payload["stops"]),
                estimate["estimated_distance_km"] if estimate["estimated_distance_km"] is not None else "",
                estimate["estimated_journey_minutes"] if estimate["estimated_journey_minutes"] is not None else "",
                estimate["departures_per_day"],
                estimate["departures_per_week"],
                SCENARIO_NOTICE,
            ]]
        )
    return buffer.getvalue()


def timetable_csv(route: dict[str, Any], timetable: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "classification",
            "route_number",
            "date",
            "trip_id",
            "headsign",
            "stop_sequence",
            "stop",
            "arrival",
            "departure",
        ]
    )
    for trip in timetable["trips"]:
        for stop in trip["stops"]:
            writer.writerow(
                [_cell(v) for v in [
                    timetable["classification"],
                    route.get("short_name") or route.get("gtfs_route_id"),
                    timetable["date"],
                    trip["trip_id"],
                    trip.get("headsign") or "",
                    stop["sequence"],
                    stop["stop"],
                    stop["arrival"] or "",
                    stop["departure"] or "",
                ]]
            )
    return buffer.getvalue()


def _table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[55 * mm, 115 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa7b4")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _document(title: str, author: str = "BMTC Future Transit Planner") -> tuple[io.BytesIO, SimpleDocTemplate]:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=title, author=author, leftMargin=20 * mm, rightMargin=20 * mm)
    return buffer, doc


def scenario_pdf(payload: dict[str, Any], estimate: dict[str, Any]) -> bytes:
    styles = getSampleStyleSheet()
    buffer, doc = _document(f"ESTIMATED SCENARIO - {payload['name']}")
    stops = "; ".join(stop["name"] for stop in payload["stops"]) or "None"
    rows = [
        ["Classification", CLASS_SCENARIO],
        ["Scenario", payload["name"]],
        ["Year", str(payload["year"])],
        ["Route code (proposed)", payload["route_code"]],
        ["Origin", payload["origin"]["name"]],
        ["Destination", payload["destination"]["name"]],
        ["Intermediate stops", stops],
        ["First departure", payload["first_departure"]],
        ["Last departure", payload["last_departure"]],
        ["Frequency", f"Every {payload['frequency_minutes']} minutes"],
        ["Operating days", ", ".join(payload["operating_days"])],
        ["Departures per day (estimate)", str(estimate["departures_per_day"])],
        [
            "Distance (estimate)",
            f"{estimate['estimated_distance_km']} km" if estimate["estimated_distance_km"] is not None else "n/a",
        ],
        [
            "Journey time (estimate)",
            f"{estimate['estimated_journey_minutes']} minutes"
            if estimate["estimated_journey_minutes"] is not None
            else "n/a",
        ],
    ]
    story = [
        Paragraph(f"<b>{escape('ESTIMATED SCENARIO')}</b>", styles["Heading2"]),
        Paragraph(escape(SCENARIO_NOTICE), styles["BodyText"]),
        Spacer(1, 6 * mm),
        _table(rows),
        Spacer(1, 6 * mm),
        Paragraph("<b>Assumptions</b>", styles["Heading3"]),
        Paragraph(escape(estimate["assumptions"]["method"]), styles["BodyText"]),
    ]
    if estimate.get("missing"):
        story.append(Paragraph(escape(estimate["missing"]), styles["BodyText"]))
    doc.build(story)
    return buffer.getvalue()


def comparison_pdf(comparison: dict[str, Any]) -> bytes:
    styles = getSampleStyleSheet()
    buffer, doc = _document("ESTIMATED SCENARIO comparison")
    a, b = comparison["a"], comparison["b"]

    def value(item: dict[str, Any], key: str) -> str:
        result = item["estimate"][key]
        return "n/a" if result is None else str(result)

    table_rows = [
        ["Measure", a["scenario"]["name"], b["scenario"]["name"]],
        ["Year", str(a["scenario"]["year"]), str(b["scenario"]["year"])],
        ["Estimated distance (km)", value(a, "estimated_distance_km"), value(b, "estimated_distance_km")],
        ["Estimated journey (min)", value(a, "estimated_journey_minutes"), value(b, "estimated_journey_minutes")],
        ["Departures per day", value(a, "departures_per_day"), value(b, "departures_per_day")],
        ["Departures per week", value(a, "departures_per_week"), value(b, "departures_per_week")],
    ]
    table = Table(table_rows, colWidths=[70 * mm, 50 * mm, 50 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa7b4")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f8")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story = [
        Paragraph(f"<b>{escape('ESTIMATED SCENARIO COMPARISON')}</b>", styles["Heading2"]),
        Paragraph(escape(SCENARIO_NOTICE), styles["BodyText"]),
        Spacer(1, 6 * mm),
        table,
    ]
    doc.build(story)
    return buffer.getvalue()

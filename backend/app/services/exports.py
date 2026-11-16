"""CSV and PDF exports. Every export carries its classification and notice."""

from __future__ import annotations

import csv
import hashlib
import io
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import CLASS_SCENARIO
from .scenarios import SCENARIO_NOTICE

# Characters that make a spreadsheet read a cell as a formula, plus the line breaks that some spreadsheets also obey.
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")
# Spaces and invisible characters that may come before a trigger. "  =1+1" must be neutralised like "=1+1".
LEADING_BLANKS = " \t\r\n\f\v\u00a0\u200b\u200c\u200d\ufeff"
PDF_FALLBACK_FONT = "Helvetica"
PDF_GLYPH_NOTICE = (
    "Some characters cannot be shown in this PDF, so they are replaced with '?'. "
    "The CSV export and the dashboard show the full text."
)
# Scripts whose letters join, reorder or change shape with their neighbours: Hebrew, Arabic, Indic, Southeast Asian and
# their presentation forms. The PDF writer draws one character at a time and does not shape or reorder text, so these
# would come out garbled even with a font that contains them. They are replaced with '?' instead.
UNSHAPED_RANGES = (
    (0x0590, 0x08FF),  # Hebrew, Arabic, Syriac, Thaana, NKo and related scripts
    (0x0900, 0x0DFF),  # Indic scripts (Devanagari for Hindi, Kannada, Tamil, Telugu, Malayalam...) and Sinhala
    (0x0E00, 0x0FFF),  # Thai, Lao and Tibetan
    (0x1000, 0x109F),  # Myanmar
    (0x1780, 0x18AF),  # Khmer and Mongolian
    (0xFB1D, 0xFDFF),  # Hebrew and Arabic presentation forms
    (0xFE70, 0xFEFF),  # Arabic presentation forms
)


def escape(text: str) -> str:
    """Escape &, < and > for ReportLab paragraph markup. These are the same three replacements that
    xml.sax.saxutils.escape makes; this module only writes text out and never parses XML."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cell(value: Any) -> str:
    """Neutralise spreadsheet formula injection: a value that starts with a formula trigger, after any leading blanks,
    gets an apostrophe in front so the spreadsheet shows it as text instead of running it."""
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip(LEADING_BLANKS)[:1] in FORMULA_TRIGGERS else text


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


# ---------------------------------------------------------------- PDF

def pdf_font(font_path: Path | None) -> str:
    """The font name to draw with. A TrueType file from PDF_FONT_PATH is registered once and used for every character
    it contains. Without one, the built-in Helvetica is used, which covers Western European text only."""
    if font_path is None:
        return PDF_FALLBACK_FONT
    name = "PlannerFont" + hashlib.sha256(str(font_path).encode("utf-8")).hexdigest()[:12]
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(font_path)))
    return name


def _in_cp1252(char: str) -> bool:
    try:
        char.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def _can_draw(font_name: str) -> Callable[[str], bool]:
    """Whether the font has a glyph for one character. Helvetica covers Windows-1252 only. A TrueType font covers
    exactly the characters in its own character map. That is checked rather than assumed, because a missing glyph
    would print as a blank."""
    if font_name == PDF_FALLBACK_FONT:
        return _in_cp1252
    glyphs = pdfmetrics.getFont(font_name).face.charToGlyph
    return lambda char: ord(char) in glyphs


def _shaped_script(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in UNSHAPED_RANGES)


def pdf_text(text: str, font_name: str) -> tuple[str, bool]:
    """Text the PDF can draw. A character it cannot draw correctly becomes '?', and the caller is told, so the PDF can
    say so. Invisible format characters (joiners, byte-order marks, soft hyphens) are dropped, since they have no shape
    of their own. Any whitespace becomes a plain space."""
    can_draw = _can_draw(font_name)
    out: list[str] = []
    replaced = False
    for char in text:
        if char.isspace():
            out.append(" ")
        elif unicodedata.category(char) == "Cf":
            continue
        elif _shaped_script(char) or not can_draw(char):
            out.append("?")
            replaced = True
        else:
            out.append(char)
    return "".join(out), replaced


class _PdfWriter:
    """Escapes and fits text for one document, and remembers whether any character had to be replaced."""

    def __init__(self, font_name: str) -> None:
        self.font = font_name
        self.replaced = False

    def text(self, value: Any) -> str:
        safe, replaced = pdf_text("" if value is None else str(value), self.font)
        self.replaced = self.replaced or replaced
        return escape(safe)


def _styles(font_name: str) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    bold = "Helvetica-Bold" if font_name == PDF_FALLBACK_FONT else font_name
    return {
        "title": ParagraphStyle("PlannerTitle", parent=sample["Heading2"], fontName=bold),
        "heading": ParagraphStyle("PlannerHeading", parent=sample["Heading3"], fontName=bold),
        "body": ParagraphStyle("PlannerBody", parent=sample["BodyText"], fontName=font_name),
        # wordWrap CJK lets a long unbroken value (a stop name with no spaces) wrap inside its cell.
        "label": ParagraphStyle("PlannerLabel", fontName=bold, fontSize=9, leading=11, wordWrap="CJK"),
        "cell": ParagraphStyle("PlannerCell", fontName=font_name, fontSize=9, leading=11, wordWrap="CJK"),
    }


def _document(title: str, author: str = "BMTC Future Transit Planner") -> tuple[io.BytesIO, SimpleDocTemplate]:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=title, author=author, leftMargin=20 * mm, rightMargin=20 * mm)
    return buffer, doc


def _label_value_table(rows: list[tuple[str, str]], writer: _PdfWriter, styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [Paragraph(writer.text(label), styles["label"]), Paragraph(writer.text(value), styles["cell"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[55 * mm, 115 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa7b4")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def scenario_pdf(payload: dict[str, Any], estimate: dict[str, Any], *, font_path: Path | None = None) -> bytes:
    font = pdf_font(font_path)
    styles = _styles(font)
    writer = _PdfWriter(font)
    buffer, doc = _document(f"ESTIMATED SCENARIO - {payload['name']}")
    stops = "; ".join(stop["name"] for stop in payload["stops"]) or "None"
    rows = [
        ("Classification", CLASS_SCENARIO),
        ("Scenario", payload["name"]),
        ("Year", str(payload["year"])),
        ("Route code (proposed)", payload["route_code"]),
        ("Origin", payload["origin"]["name"]),
        ("Destination", payload["destination"]["name"]),
        ("Intermediate stops", stops),
        ("First departure", payload["first_departure"]),
        ("Last departure", payload["last_departure"]),
        ("Frequency", f"Every {payload['frequency_minutes']} minutes"),
        ("Operating days", ", ".join(payload["operating_days"])),
        ("Departures per day (estimate)", str(estimate["departures_per_day"])),
        (
            "Distance (estimate)",
            f"{estimate['estimated_distance_km']} km" if estimate["estimated_distance_km"] is not None else "n/a",
        ),
        (
            "Journey time (estimate)",
            f"{estimate['estimated_journey_minutes']} minutes"
            if estimate["estimated_journey_minutes"] is not None
            else "n/a",
        ),
    ]
    story: list[Any] = [
        Paragraph(f"<b>{escape('ESTIMATED SCENARIO')}</b>", styles["title"]),
        Paragraph(writer.text(SCENARIO_NOTICE), styles["body"]),
        Spacer(1, 6 * mm),
        _label_value_table(rows, writer, styles),
        Spacer(1, 6 * mm),
        Paragraph("Assumptions", styles["heading"]),
        Paragraph(writer.text(estimate["assumptions"]["method"]), styles["body"]),
    ]
    if estimate.get("missing"):
        story.append(Paragraph(writer.text(estimate["missing"]), styles["body"]))
    if writer.replaced:
        story.append(Paragraph(escape(PDF_GLYPH_NOTICE), styles["body"]))
    doc.build(story)
    return buffer.getvalue()


def comparison_pdf(comparison: dict[str, Any], *, font_path: Path | None = None) -> bytes:
    font = pdf_font(font_path)
    styles = _styles(font)
    writer = _PdfWriter(font)
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
    data = [
        [Paragraph(writer.text(cell), styles["label"] if row_index == 0 or column == 0 else styles["cell"])
         for column, cell in enumerate(row)]
        for row_index, row in enumerate(table_rows)
    ]
    table = Table(data, colWidths=[70 * mm, 50 * mm, 50 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa7b4")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story: list[Any] = [
        Paragraph(f"<b>{escape('ESTIMATED SCENARIO COMPARISON')}</b>", styles["title"]),
        Paragraph(writer.text(SCENARIO_NOTICE), styles["body"]),
        Spacer(1, 6 * mm),
        table,
    ]
    if writer.replaced:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(escape(PDF_GLYPH_NOTICE), styles["body"]))
    doc.build(story)
    return buffer.getvalue()

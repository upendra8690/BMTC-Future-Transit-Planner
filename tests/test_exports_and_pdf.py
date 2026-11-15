"""CSV and PDF exports: spreadsheet formula protection, the text a PDF can draw, and an optional TrueType font.

Scenarios and timetables carry text that people typed or that a feed supplied, so these tests use hostile and non-Latin
text on purpose. Every non-ASCII character is built with chr(), so the test source contains no invisible characters.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from app.main import create_app
from app.services.exports import PDF_FALLBACK_FONT, _cell, pdf_font, pdf_text
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics

from tests.helpers import CLIENT_A, admin_headers, client_headers, make_settings, valid_files, zip_of

DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
needs_dejavu = pytest.mark.skipif(not DEJAVU.is_file(), reason="DejaVu Sans is not installed on this machine")
NOTICE_START = "cannot be shown in this PDF"

E_ACUTE = chr(0xE9)  # e with acute accent, in Windows-1252
EURO = chr(0x20AC)  # euro sign, in Windows-1252
SHARP_S = chr(0xDF)  # German sharp s, in Windows-1252
OMEGA = chr(0x03A9)  # Greek capital omega, not in Windows-1252
CJK = chr(0x4E2D)  # a Chinese character, not in Windows-1252
KANNADA_KA = chr(0x0C95)  # a Kannada letter that DejaVu Sans does not contain
KANNADA_MA = chr(0x0CAE)  # a second Kannada letter
ARABIC_ALEF = chr(0x0627)  # an Arabic letter that DejaVu Sans does contain
NBSP = chr(0xA0)  # no-break space
ZWSP = chr(0x200B)  # zero-width space
ZWJ = chr(0x200D)  # zero-width joiner
SOFT_HYPHEN = chr(0xAD)  # soft hyphen
BOM = chr(0xFEFF)  # byte-order mark


def _scenario(name: str = "Trial route", **overrides) -> dict:
    body = {
        "name": name,
        "year": 2028,
        "route_code": "PROP-1",
        "origin_name": "Demo Central",
        "origin_lat": 12.975,
        "origin_lon": 77.595,
        "destination_name": "Demo Junction",
        "destination_lat": 12.998,
        "destination_lon": 77.624,
        "first_departure": "06:00",
        "last_departure": "22:00",
        "frequency_minutes": 15,
        "operating_days": ["MON", "TUE", "WED", "THU", "FRI"],
        "stops": [{"name": "Demo Market", "lat": 12.979, "lon": 77.600}],
    }
    body.update(overrides)
    return body


def _create(client: TestClient, **overrides) -> int:
    created = client.post("/api/scenarios", headers=client_headers(CLIENT_A), json=_scenario(**overrides))
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _pdf_words(data: bytes) -> str:
    """The text a reader would extract from the PDF, with spacing normalised."""
    reader = PdfReader(io.BytesIO(data))
    return " ".join(" ".join(page.extract_text() for page in reader.pages).split())


def _scenario_pdf(client: TestClient, scenario_id: int) -> str:
    response = client.get(f"/api/scenarios/{scenario_id}/export.pdf", headers=client_headers(CLIENT_A))
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    return _pdf_words(response.content)


# ------------------------------------------------------------------ CSV: spreadsheet formulas


@pytest.mark.parametrize(
    "value",
    ["=1+1", "+1", "-1", "@SUM(A1)", "\t=cmd", "\r=cmd", "\n=cmd", "  =SUM(A1)", NBSP + "=1", ZWSP + "=1", BOM + "=1"],
)
def test_values_that_would_run_as_formulas_are_marked_as_text(value):
    assert _cell(value) == "'" + value


@pytest.mark.parametrize(
    "value", ["Majestic", "Caf" + E_ACUTE, "1-2", "10", "3.5", KANNADA_KA + chr(0x0CC6), "", None, 15]
)
def test_ordinary_values_are_written_unchanged(value):
    assert _cell(value) == ("" if value is None else str(value))


def test_a_hostile_scenario_name_cannot_shift_columns_or_run(client):
    hostile = '=HYPERLINK("https://example.invalid","open"),extra'
    _create(client, name=hostile)
    export = client.get("/api/scenarios/export.csv", headers=client_headers(CLIENT_A))
    assert export.status_code == 200
    rows = list(csv.reader(io.StringIO(export.text)))
    header, body = rows[0], rows[1]
    assert len(body) == len(header)  # the comma inside the name did not add a column
    assert body[header.index("name")] == "'" + hostile


def test_a_hostile_stop_name_in_a_timetable_is_marked_as_text(client):
    hostile = '=HYPERLINK("https://example.invalid")'
    files = valid_files()
    quoted = '"' + hostile.replace('"', '""') + '"'  # a CSV field with quotes must be wrapped and its quotes doubled
    files["stops.txt"] = files["stops.txt"].replace("Alpha", quoted)
    source = client.post(
        "/api/admin/data-sources",
        json={"name": "Feed", "publisher": "Test", "kind": "COMMUNITY", "license": "test"},
        headers=admin_headers(),
    ).json()
    upload = client.post(
        "/api/admin/imports",
        files={"file": ("feed.zip", zip_of(files), "application/zip")},
        data={"data_source_id": str(source["id"])},
        headers=admin_headers(),
    )
    assert upload.status_code == 201, upload.text
    route = client.get(
        "/api/routes", params={"classification": "UNVERIFIED_FEED", "year": 2027, "q": "Test Route"}
    ).json()["results"][0]
    export = client.get(f"/api/routes/{route['id']}/timetable.csv", params={"date": "2027-01-11"})
    assert export.status_code == 200
    rows = list(csv.reader(io.StringIO(export.text)))
    stop_column = rows[0].index("stop")
    stops = {row[stop_column] for row in rows[1:]}
    assert "'" + hostile in stops
    assert hostile not in stops


def test_the_csv_keeps_the_full_non_latin_text(client):
    name = "Trial " + KANNADA_KA + KANNADA_MA
    _create(client, name=name)
    export = client.get("/api/scenarios/export.csv", headers=client_headers(CLIENT_A))
    assert name in export.text


# ------------------------------------------------------------------ PDF: the text the writer can draw


def test_helvetica_keeps_western_text_and_replaces_other_scripts():
    kept = "Caf" + E_ACUTE + " " + EURO + " " + SHARP_S
    assert pdf_text(kept, PDF_FALLBACK_FONT) == (kept, False)
    assert pdf_text(KANNADA_KA + KANNADA_MA, PDF_FALLBACK_FONT) == ("??", True)
    assert pdf_text(CJK, PDF_FALLBACK_FONT) == ("?", True)


def test_whitespace_becomes_a_space_and_invisible_characters_disappear():
    assert pdf_text("a\tb\nc", PDF_FALLBACK_FONT) == ("a b c", False)
    hidden = "a" + ZWSP + "b" + ZWJ + "c" + SOFT_HYPHEN + "d" + BOM + "e"
    assert pdf_text(hidden, PDF_FALLBACK_FONT) == ("abcde", False)


def test_no_font_path_means_the_standard_font():
    assert pdf_font(None) == PDF_FALLBACK_FONT


@needs_dejavu
def test_a_truetype_font_draws_the_characters_it_contains():
    name = pdf_font(DEJAVU)
    assert name != PDF_FALLBACK_FONT
    assert pdf_font(DEJAVU) == name  # registering the same file twice gives the same name
    text = "Caf" + E_ACUTE + " " + OMEGA
    assert pdf_text(text, name) == (text, False)


@needs_dejavu
def test_a_character_missing_from_the_font_is_replaced_and_reported():
    name = pdf_font(DEJAVU)
    assert ord(KANNADA_KA) not in pdfmetrics.getFont(name).face.charToGlyph
    assert pdf_text(KANNADA_KA, name) == ("?", True)


@needs_dejavu
def test_complex_scripts_are_replaced_even_when_the_font_has_the_letters():
    name = pdf_font(DEJAVU)
    assert ord(ARABIC_ALEF) in pdfmetrics.getFont(name).face.charToGlyph  # the font does have this letter...
    assert pdf_text(ARABIC_ALEF, name) == ("?", True)  # ...but joined scripts are not drawn one letter at a time


# ------------------------------------------------------------------ PDF: what a reader sees


def test_a_long_unbroken_stop_name_wraps_inside_its_cell(client):
    scenario_id = _create(client, name="Wrap test", stops=[{"name": "Q" * 100}])
    assert _scenario_pdf(client, scenario_id).replace(" ", "").count("Q") == 100


def test_the_pdf_says_when_characters_were_replaced(client):
    scenario_id = _create(client, name="Trial " + KANNADA_KA + KANNADA_MA)
    text = _scenario_pdf(client, scenario_id)
    assert "Trial" in text
    assert NOTICE_START in text
    assert not any(0x0C80 <= ord(char) <= 0x0CFF for char in text)  # no Kannada letters reach the page text


def test_the_pdf_has_no_notice_when_everything_can_be_drawn(client):
    scenario_id = _create(client, name="Caf" + E_ACUTE + " trial")
    text = _scenario_pdf(client, scenario_id)
    assert "Caf" + E_ACUTE in text
    assert NOTICE_START not in text


def test_the_comparison_pdf_gives_the_same_notice(client):
    first = _create(client, name="Trial " + KANNADA_KA)
    second = _create(client, name="Second route", frequency_minutes=30)
    response = client.get(
        "/api/scenarios/compare.pdf", headers=client_headers(CLIENT_A), params={"a": first, "b": second}
    )
    assert response.status_code == 200
    assert NOTICE_START in _pdf_words(response.content)


@needs_dejavu
def test_the_configured_font_is_used_and_missing_glyphs_are_still_reported(tmp_path):
    root = tmp_path / "ttf"
    root.mkdir()
    app = create_app(make_settings(root, pdf_font_path=DEJAVU))
    try:
        with TestClient(app) as client:
            plain_id = _create(client, name="Caf" + E_ACUTE + " trial")
            mixed_id = _create(client, name="Trial " + KANNADA_KA)
            plain_text = _scenario_pdf(client, plain_id)
            mixed_text = _scenario_pdf(client, mixed_id)
        assert "Caf" + E_ACUTE in plain_text
        assert NOTICE_START not in plain_text
        assert NOTICE_START in mixed_text
    finally:
        app.state.db.dispose()

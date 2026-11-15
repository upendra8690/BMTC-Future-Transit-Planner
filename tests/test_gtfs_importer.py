"""GTFS importer: validation, hostile archives, classification and transactional safety."""

from __future__ import annotations

import datetime as dt
import io
import json
import warnings
import zipfile

import pytest
from app.gtfs import importer
from app.gtfs.importer import import_feed, parse_gtfs_date, parse_gtfs_time
from app.models import (
    CLASS_OFFICIAL,
    CLASS_UNVERIFIED,
    KIND_OFFICIAL,
    KIND_SYNTHETIC,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    GtfsImport,
    Route,
    StopTime,
)
from sqlalchemy import func, select

from tests.helpers import (
    FEED_END,
    FEED_START,
    TODAY,
    make_settings,
    make_source,
    synthetic_feed,
    valid_files,
    zip_of,
)


def run_import(session, data: bytes, source, settings, *, today: dt.date = TODAY) -> GtfsImport:
    return import_feed(session, data, filename="feed.zip", source=source, settings=settings, today=today)


def error_text(imp: GtfsImport) -> str:
    return " | ".join(json.loads(imp.errors))


def warning_text(imp: GtfsImport) -> str:
    return " | ".join(json.loads(imp.warnings))


def assert_rejected(database, settings, files: dict[str, str], fragment: str) -> None:
    """A broken feed is stored as REJECTED with a reason, and none of its rows reach the timetable."""
    with database.session() as session:
        imp = run_import(session, zip_of(files), make_source(session), settings)
        assert imp.status == STATUS_REJECTED, error_text(imp)
        assert fragment in error_text(imp), error_text(imp)
        assert session.scalar(select(func.count(Route.id))) == 0
        assert session.scalar(select(func.count(StopTime.id))) == 0


# ---------------------------------------------------------------- parsing rules

def test_gtfs_times_may_run_past_midnight():
    assert parse_gtfs_time("25:30:00") == 25 * 3600 + 30 * 60
    assert parse_gtfs_time("24:00:00") == 24 * 3600


@pytest.mark.parametrize("value", ["8:00", "12:60:00", "08-00-00", "25:xx:00", ""])
def test_malformed_gtfs_times_are_refused(value):
    assert parse_gtfs_time(value) is None


def test_gtfs_dates_must_be_real_calendar_dates():
    assert parse_gtfs_date("20270101") == dt.date(2027, 1, 1)
    for value in ["2027-01-01", "20271301", "20270230", "1999", ""]:
        assert parse_gtfs_date(value) is None, value


# ---------------------------------------------------------------- classification

def test_valid_demo_feed_is_imported_as_unverified_with_exact_counts(database, settings):
    with database.session() as session:
        source = make_source(session, kind=KIND_SYNTHETIC)
        imp = run_import(session, synthetic_feed(), source, settings)
        assert imp.status == STATUS_COMPLETED, error_text(imp)
        assert imp.classification == CLASS_UNVERIFIED
        assert imp.feed_start_date == FEED_START
        assert imp.feed_end_date == FEED_END
        # Per route and direction: 33 half-hourly weekday trips plus 15 hourly weekend trips.
        assert imp.route_count == 2
        assert imp.stop_count == 6
        assert imp.trip_count == 2 * 2 * (33 + 15)
        # Route 1 has six stops and route 2 has four, each run 48 times per direction.
        assert imp.stop_time_count == 2 * 48 * 6 + 2 * 48 * 4
        assert imp.shape_point_count == 6 + 6 + 4 + 4


def test_official_classification_needs_an_official_and_verified_source(database, settings):
    with database.session() as session:
        unverified_official = make_source(session, kind=KIND_OFFICIAL, verified=False)
        assert run_import(session, synthetic_feed(), unverified_official, settings).classification == CLASS_UNVERIFIED

        verified_official = make_source(session, kind=KIND_OFFICIAL, verified=True)
        imp = run_import(session, synthetic_feed(holiday=dt.date(2027, 1, 26)), verified_official, settings)
        assert imp.classification == CLASS_OFFICIAL


def test_valid_minimal_feed_is_accepted(database, settings):
    with database.session() as session:
        imp = run_import(session, zip_of(valid_files()), make_source(session), settings)
        assert imp.status == STATUS_COMPLETED, error_text(imp)
        assert imp.trip_count == 1
        assert imp.stop_time_count == 2


# ---------------------------------------------------------------- hostile archives

@pytest.mark.parametrize("data", [b"", b"this is not a zip file"], ids=["empty", "not-a-zip"])
def test_unreadable_archive_is_rejected(database, settings, data):
    with database.session() as session:
        imp = run_import(session, data, make_source(session), settings)
        assert imp.status == STATUS_REJECTED
        assert "not a readable ZIP" in error_text(imp)


def test_path_traversal_member_rejects_the_feed(database, settings):
    files = {**valid_files(), "../escape.txt": "malicious"}
    with database.session() as session:
        imp = run_import(session, zip_of(files), make_source(session), settings)
        assert imp.status == STATUS_REJECTED
        assert "unsafe file path" in error_text(imp)


def test_absolute_path_member_rejects_the_feed(database, settings):
    files = {**valid_files(), "/etc/evil.txt": "malicious"}
    with database.session() as session:
        imp = run_import(session, zip_of(files), make_source(session), settings)
        assert imp.status == STATUS_REJECTED
        assert "unsafe file path" in error_text(imp)


def test_duplicate_member_rejects_the_feed(database, settings):
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # zipfile warns about duplicate names
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in valid_files().items():
                archive.writestr(name, content)
            archive.writestr("stops.txt", valid_files()["stops.txt"])
    with database.session() as session:
        imp = run_import(session, buffer.getvalue(), make_source(session), settings)
        assert imp.status == STATUS_REJECTED
        assert "appears more than once" in error_text(imp)


def test_suspicious_compression_ratio_is_rejected(database, settings):
    files = {**valid_files(), "notes.txt": "A" * 2_000_000}  # compresses to a few kilobytes
    with database.session() as session:
        imp = run_import(session, zip_of(files), make_source(session), settings)
        assert imp.status == STATUS_REJECTED
        assert "suspicious compression ratio" in error_text(imp)


def test_uncompressed_size_limit_is_enforced(database, tmp_path):
    tight = make_settings(tmp_path, max_uncompressed_bytes=1024)
    with database.session() as session:
        imp = run_import(session, synthetic_feed(), make_source(session), tight)
        assert imp.status == STATUS_REJECTED
        assert "configured limit" in error_text(imp)


def test_member_count_limit_is_enforced(database, tmp_path):
    limited = make_settings(tmp_path, max_zip_members=3)
    with database.session() as session:
        imp = run_import(session, zip_of(valid_files()), make_source(session), limited)
        assert imp.status == STATUS_REJECTED
        assert "the limit is 3" in error_text(imp)


# ---------------------------------------------------------------- referential and structural checks

def test_missing_required_file_rejects_the_whole_feed(database, settings):
    files = valid_files()
    del files["trips.txt"]
    assert_rejected(database, settings, files, "trips.txt")


def test_unknown_route_id_on_a_trip_is_rejected(database, settings):
    files = valid_files()
    files["trips.txt"] = files["trips.txt"].replace("R1,WK", "NOPE,WK")
    assert_rejected(database, settings, files, "unknown route_id")


def test_unknown_trip_id_in_stop_times_is_rejected(database, settings):
    files = valid_files()
    files["stop_times.txt"] = files["stop_times.txt"].replace("T1,08:00:00", "TX,08:00:00", 1)
    assert_rejected(database, settings, files, "unknown trip_id")


def test_unknown_stop_id_in_stop_times_is_rejected(database, settings):
    files = valid_files()
    files["stop_times.txt"] = files["stop_times.txt"].replace("S2,2", "SX,2")
    assert_rejected(database, settings, files, "unknown stop_id")


def test_stop_sequence_must_increase_within_a_trip(database, settings):
    files = valid_files()
    files["stop_times.txt"] = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S1,2\nT1,08:10:00,08:10:00,S2,1\n"
    )
    assert_rejected(database, settings, files, "stop_sequence must increase")


@pytest.mark.parametrize("bad", ["25:xx:00", "8:00", "08-00-00"])
def test_malformed_stop_times_are_rejected(database, settings, bad):
    files = valid_files()
    files["stop_times.txt"] = files["stop_times.txt"].replace("08:00:00,08:00:00,S1", f"{bad},{bad},S1", 1)
    assert_rejected(database, settings, files, "HH:MM:SS")


def test_departure_before_arrival_is_rejected(database, settings):
    files = valid_files()
    files["stop_times.txt"] = files["stop_times.txt"].replace("08:00:00,08:00:00,S1", "08:05:00,08:00:00,S1", 1)
    assert_rejected(database, settings, files, "earlier than arrival")


def test_stop_times_with_no_rows_are_rejected(database, settings):
    files = valid_files()
    files["stop_times.txt"] = "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
    assert_rejected(database, settings, files, "no rows")


def test_stop_without_coordinates_is_rejected(database, settings):
    files = valid_files()
    files["stops.txt"] = "stop_id,stop_name,stop_lat,stop_lon,location_type\nS1,Alpha,,,0\nS2,Beta,12.98,77.60,0\n"
    assert_rejected(database, settings, files, "valid coordinates")


def test_out_of_range_coordinates_are_rejected(database, settings):
    files = valid_files()
    files["stops.txt"] = (
        "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
        "S1,Alpha,123.0,77.59,0\n"
        "S2,Beta,12.98,77.60,0\n"
    )
    assert_rejected(database, settings, files, "valid coordinates")


def test_invalid_calendar_date_is_rejected(database, settings):
    files = valid_files()
    files["calendar.txt"] = files["calendar.txt"].replace("20270101", "2027-01-01")
    assert_rejected(database, settings, files, "YYYYMMDD")


def test_inverted_service_window_is_rejected(database, settings):
    files = valid_files()
    files["calendar.txt"] = files["calendar.txt"].replace("20270101,20271231", "20271231,20270101")
    assert_rejected(database, settings, files, "after end_date")


def test_weekday_flags_must_be_zero_or_one(database, settings):
    files = valid_files()
    files["calendar.txt"] = files["calendar.txt"].replace("WK,1,1,1,1,1,0,0", "WK,1,1,1,1,1,0,2")
    assert_rejected(database, settings, files, "weekday columns must be 0 or 1")


# ---------------------------------------------------------------- warnings and transactions

def test_expired_feed_is_kept_with_a_warning(database, settings):
    files = valid_files()
    files["calendar.txt"] = files["calendar.txt"].replace("20270101,20271231", "20200101,20201231")
    with database.session() as session:
        imp = run_import(session, zip_of(files), make_source(session), settings)
        assert imp.status == STATUS_COMPLETED, error_text(imp)
        assert "before today" in warning_text(imp)


def test_overlapping_imports_of_one_classification_are_flagged(database, settings):
    with database.session() as session:
        source = make_source(session)
        run_import(session, synthetic_feed(), source, settings)
        second = run_import(session, synthetic_feed(holiday=dt.date(2027, 1, 4)), source, settings)
        assert second.status == STATUS_COMPLETED
        assert "Dates overlap" in warning_text(second)


def test_identical_file_is_flagged_on_second_import(database, settings):
    data = zip_of(valid_files())
    with database.session() as session:
        source = make_source(session)
        first = run_import(session, data, source, settings)
        second = run_import(session, data, source, settings)
        assert first.status == second.status == STATUS_COMPLETED
        assert "identical file" in warning_text(second)


def test_failed_write_rolls_back_every_row(database, settings, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(importer, "_insert_feed", explode)
    with database.session() as session:
        imp = run_import(session, zip_of(valid_files()), make_source(session), settings)
        assert imp.status == STATUS_REJECTED
        assert "see the server log" in error_text(imp).lower()
        assert session.scalar(select(func.count(Route.id))) == 0
        assert session.scalar(select(func.count(StopTime.id))) == 0

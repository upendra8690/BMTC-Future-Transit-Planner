"""Regression tests for defects found by probing the v1 importer. Each test names the defect it guards against."""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
import json

import pytest
from app import clock
from app.gtfs import importer
from app.gtfs.importer import FeedTooLargeError, _BudgetedReader, _ReadBudget
from app.models import KIND_COMMUNITY, GtfsImport, Stop
from sqlalchemy import select

from tests.helpers import make_source, valid_files, zip_of


def _import(database, settings, files: dict[str, str], *, today: dt.date | None = None) -> GtfsImport:
    session = database.session()
    try:
        source = make_source(session, kind=KIND_COMMUNITY)
        imp = importer.import_feed(
            session, zip_of(files), filename="regression.zip", source=source, settings=settings, today=today
        )
        session.expunge(imp)
        return imp
    finally:
        session.close()


def _errors(imp: GtfsImport) -> list[str]:
    return json.loads(imp.errors or "[]")


def _warnings(imp: GtfsImport) -> list[str]:
    return json.loads(imp.warnings or "[]")


def _in_zone(files: dict[str, str], zone: str) -> dict[str, str]:
    """A copy of the feed with its agency in the given time zone."""
    updated = dict(files)
    updated["agency.txt"] = f"agency_id,agency_name,agency_url,agency_timezone\nT,Test Agency,https://example.invalid,{zone}\n"
    return updated


def test_identifier_longer_than_the_column_is_refused_with_its_real_reason(database, settings):
    """v1 stored a 101-character route id cut to 100 characters, then failed to find it and blamed the database."""
    long_id = "R" * 101
    files = valid_files()
    files["routes.txt"] = f"route_id,route_short_name,route_long_name,route_type\n{long_id},T-1,Test Route,3\n"
    files["trips.txt"] = f"route_id,service_id,trip_id,direction_id\n{long_id},WK,T1,0\n"
    imp = _import(database, settings, files)
    assert imp.status == "REJECTED"
    assert any("route_id is longer than 100 characters" in e for e in _errors(imp)), _errors(imp)
    assert not any("failed while writing" in e for e in _errors(imp))


def test_superscript_two_in_route_type_is_refused_not_mistaken_for_a_number(database, settings):
    """str.isdigit() accepts superscript two, but int() cannot read it, so v1 failed with the wrong message."""
    files = valid_files()
    files["routes.txt"] = "route_id,route_short_name,route_long_name,route_type\nR1,T-1,Test Route,²\n"
    imp = _import(database, settings, files)
    assert imp.status == "REJECTED"
    assert any("route_type must be a whole number" in e for e in _errors(imp)), _errors(imp)


def test_superscript_two_in_stop_sequence_does_not_crash_the_import(database, settings):
    """v1 raised an unhandled ValueError here, which the API turned into a server error."""
    files = valid_files()
    files["stop_times.txt"] = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S1,1\nT1,08:10:00,08:10:00,S2,²\n"
    )
    imp = _import(database, settings, files)
    assert imp.status == "REJECTED"
    assert any("stop_sequence must be a whole number" in e for e in _errors(imp)), _errors(imp)


def test_superscript_two_in_shape_sequence_is_refused(database, settings):
    files = valid_files()
    files["shapes.txt"] = "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nSH1,12.9,77.6,²\n"
    files["trips.txt"] = "route_id,service_id,trip_id,direction_id,shape_id\nR1,WK,T1,0,SH1\n"
    imp = _import(database, settings, files)
    assert imp.status == "REJECTED"
    assert any("shape_pt_sequence must be a whole number" in e for e in _errors(imp)), _errors(imp)


def test_other_scripts_digits_are_not_accepted_as_gtfs_times(database, settings):
    files = valid_files()
    files["stop_times.txt"] = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,٠٨:00:00,٠٨:00:00,S1,1\nT1,08:10:00,08:10:00,S2,2\n"
    )
    imp = _import(database, settings, files)
    assert imp.status == "REJECTED"
    assert any("is not HH:MM:SS" in e for e in _errors(imp)), _errors(imp)


def test_unknown_agency_timezone_is_refused_before_it_can_break_the_clock(database, settings):
    """v1 accepted any text as agency_timezone; a bad zone would later make every 'now' answer wrong."""
    files = valid_files()
    files["agency.txt"] = "agency_id,agency_name,agency_url,agency_timezone\nT,Test Agency,https://example.invalid,Mars/Olympus\n"
    imp = _import(database, settings, files)
    assert imp.status == "REJECTED"
    assert any("not a known IANA time zone" in e for e in _errors(imp)), _errors(imp)


def test_agencies_in_one_feed_must_share_a_time_zone(database, settings):
    files = valid_files()
    files["agency.txt"] = (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "A,First,https://example.invalid,Asia/Kolkata\n"
        "B,Second,https://example.invalid,Europe/London\n"
    )
    imp = _import(database, settings, files)
    assert imp.status == "REJECTED"
    assert any("more than one agency_timezone" in e for e in _errors(imp)), _errors(imp)


def test_older_zone_name_is_accepted_and_stored(database, settings):
    files = valid_files()
    files["agency.txt"] = "agency_id,agency_name,agency_url,agency_timezone\nT,Test Agency,https://example.invalid,Asia/Calcutta\n"
    imp = _import(database, settings, files)
    assert imp.status == "COMPLETED", _errors(imp)


def test_times_that_go_backwards_are_warned_about_and_the_feed_is_still_kept(database, settings):
    files = valid_files()
    files["stop_times.txt"] = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S1,1\nT1,07:50:00,07:50:00,S2,2\n"
    )
    imp = _import(database, settings, files)
    assert imp.status == "COMPLETED", _errors(imp)
    assert any("earlier than the stop before" in w for w in _warnings(imp)), _warnings(imp)


def test_names_are_stored_in_one_unicode_form(database, settings):
    files = valid_files()
    files["stops.txt"] = (
        "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
        "S1,Café  Corner,12.97,77.59,0\n"
        "S2,Beta,12.98,77.60,0\n"
    )
    imp = _import(database, settings, files)
    assert imp.status == "COMPLETED", _errors(imp)
    session = database.session()
    try:
        names = set(session.scalars(select(Stop.name).where(Stop.import_id == imp.id)))
    finally:
        session.close()
    assert "Café Corner" in names
    assert "Café Corner" not in names


def test_feed_end_date_is_judged_in_the_feed_time_zone_not_on_the_server(database, settings, monkeypatch):
    """At 20:00 UTC on 15 November it is already 16 November in India. A feed ending on the 15th has expired there."""
    files = _in_zone(valid_files(), "Asia/Kolkata")
    files["calendar.txt"] = (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "WK,1,1,1,1,1,0,0,20260101,20261115\n"
    )
    monkeypatch.setattr(clock, "utc_now", lambda: dt.datetime(2026, 11, 15, 20, 0, tzinfo=dt.UTC))
    imp = _import(database, settings, files)
    assert imp.status == "COMPLETED", _errors(imp)
    assert any("before today" in w for w in _warnings(imp)), _warnings(imp)


def test_feed_end_date_is_not_expired_while_it_is_still_today_in_the_feed_zone(database, settings, monkeypatch):
    """At 03:00 UTC on 16 November it is still 15 November in New York, so the feed is current there."""
    files = _in_zone(valid_files(), "America/New_York")
    files["calendar.txt"] = (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "WK,1,1,1,1,1,0,0,20260101,20261115\n"
    )
    monkeypatch.setattr(clock, "utc_now", lambda: dt.datetime(2026, 11, 16, 3, 0, tzinfo=dt.UTC))
    imp = _import(database, settings, files)
    assert imp.status == "COMPLETED", _errors(imp)
    assert not any("before today" in w for w in _warnings(imp)), _warnings(imp)


def test_an_explicit_today_still_overrides_the_clock(database, settings, monkeypatch):
    """With the clock at 1 December the feed would be expired, so only the explicit date keeps it current."""
    monkeypatch.setattr(clock, "utc_now", lambda: dt.datetime(2026, 12, 1, 0, 0, tzinfo=dt.UTC))
    files = valid_files()
    files["calendar.txt"] = (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "WK,1,1,1,1,1,0,0,20260101,20261115\n"
    )
    imp = _import(database, settings, files, today=dt.date(2026, 11, 15))
    assert imp.status == "COMPLETED", _errors(imp)
    assert not any("before today" in w for w in _warnings(imp))


def test_reading_stops_when_the_real_size_is_over_the_limit():
    """ZIP headers can understate the decompressed size, so the bytes actually read are counted as well."""
    reader = io.BufferedReader(_BudgetedReader(io.BytesIO(b"x" * 100), _ReadBudget(40)))
    with pytest.raises(FeedTooLargeError, match="larger than the configured limit"):
        reader.read()


def test_reading_within_the_limit_is_unchanged():
    reader = io.BufferedReader(_BudgetedReader(io.BytesIO(b"abc" * 10), _ReadBudget(100)))
    assert reader.read() == b"abc" * 10


def test_a_feed_over_the_uncompressed_limit_is_rejected_with_the_reason(database, settings):
    files = valid_files()
    tight = dataclasses.replace(settings, max_uncompressed_bytes=200)
    imp = _import(database, tight, files)
    assert imp.status == "REJECTED"
    assert any("larger than the configured limit" in e for e in _errors(imp)), _errors(imp)


def test_the_valid_baseline_feed_still_imports(database, settings):
    """The smallest passing feed must keep passing: the regression rules must not reject good data."""
    imp = _import(database, settings, valid_files())
    assert imp.status == "COMPLETED", _errors(imp)
